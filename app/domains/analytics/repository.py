import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.aggregation import (
    bucket_for,
    bucket_starts,
    fit_score_bands,
    period_start,
    rate,
    weighted_average,
)
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.models import Application
from app.domains.assessments.attempts.enums import AttemptStatus, TemplateType
from app.domains.assessments.attempts.models import (
    AssessmentAttempt,
    AssessmentAttemptReopen,
)
from app.domains.auth.models import User
from app.domains.company_addresses.models import CompanyAddress

# analytics is the one read-only cross-domain reporting layer: it queries other
# domains' models directly (here, the evaluations domain) rather than going
# through their repositories/services. It owns no write paths, so this stays
# consistent with how it already reaches into job_posts / assessments / etc.
from app.domains.evaluations.models import (
    ApplicationEvaluation,
    ApplicationEvaluationScore,
)
from app.domains.job_posts.enums import JobPostStatus
from app.domains.job_posts.models import JobPost
from app.domains.positions.models import Position

_ACTIVE_APPLICATION_STATUSES = (
    ApplicationStatus.APPLIED.value,
    ApplicationStatus.PRESCREENING.value,
    ApplicationStatus.INTERVIEW.value,
)

# The role-performance table is a leaderboard, not an inventory — cap it so a
# large closed-role backlog can't bloat the payload or the page.
_ROLE_LIMIT = 20

# Thresholds behind the recruitment report's "recommendation" column — a
# plain, deterministic decision tree over the numbers already on the report,
# not a black box. Tune these constants as hiring norms change; there's
# nothing "learned" here to retrain.
_REC_PASSED_ENOUGH = 3  # passed candidates at which a role is likely staffed
_REC_LOW_TURNOUT = 5  # applications below this count as "still quiet"
_REC_STALE_DAYS = 30  # days live before a quiet posting is "stale"
_REC_HIGH_SCORE = 80.0  # average fit score counted as "strong pool"
_REC_LOW_SCREEN_RATE = 0.3  # screened/applied below this flags a mismatch


def _recommend(
    *,
    status: str,
    applied: int,
    screened: int,
    passed: int,
    accepted: int,
    avg_score: float | None,
    posting_duration_days: int | None,
) -> str | None:
    """One of the six actions HR can take on a posting, or `None` for a
    draft/closed post (nothing to act on day-to-day). First matching rule
    wins — see the module constants above for the thresholds."""
    if status != JobPostStatus.PUBLISHED.value:
        return None
    if passed >= _REC_PASSED_ENOUGH or accepted >= 1:
        return "Close the posting after sufficient qualified applicants are identified"
    if avg_score is not None and avg_score >= _REC_HIGH_SCORE and passed > 0:
        return "Prioritize high-scoring candidates"
    if passed > 0:
        return "Schedule interviews"
    if applied < _REC_LOW_TURNOUT:
        if (
            posting_duration_days is not None
            and posting_duration_days >= _REC_STALE_DAYS
        ):
            return "Extend the posting period"
        return "Continue promoting the posting"
    if applied and (screened / applied) < _REC_LOW_SCREEN_RATE:
        return "Review job requirements"
    return "Continue promoting the posting"


class AnalyticsRepository:
    """Read-only aggregate queries across the existing ATS domains."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _application_filters(
        self,
        *,
        period: str,
        position_id: uuid.UUID | None,
    ) -> list:
        filters: list = []
        start = period_start(period)
        if start is not None:
            filters.append(Application.created_at >= start)
        if position_id is not None:
            filters.append(
                Application.job_post_id.in_(
                    select(JobPost.id).where(JobPost.position_id == position_id)
                )
            )
        return filters

    async def overview(
        self,
        *,
        period: str,
        position_id: uuid.UUID | None,
    ) -> dict:
        filters = self._application_filters(period=period, position_id=position_id)
        hiring = await self._hiring(filters=filters, period=period)
        roles = await self._roles(filters=filters, position_id=position_id)
        assessments = await self._assessments(filters=filters)
        evaluations = await self._evaluations(
            period=period,
            position_id=position_id,
        )
        return {
            "period": period,
            "position_id": position_id,
            "hiring": hiring,
            "roles": roles,
            "assessments": assessments,
            "evaluations": evaluations,
        }

    async def _hiring(self, *, filters: list, period: str) -> dict:
        row = (
            await self.db.execute(
                select(
                    func.count(Application.id).label("total_applications"),
                    func.count(func.distinct(Application.applicant_id)).label(
                        "unique_applicants"
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    Application.status.in_(
                                        _ACTIVE_APPLICATION_STATUSES
                                    ),
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("active_candidates"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    Application.status
                                    == ApplicationStatus.SUCCESS.value,
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("hires"),
                ).where(*filters)
            )
        ).one()
        total = int(row.total_applications)
        hires = int(row.hires)

        status_counts = {status.value: 0 for status in ApplicationStatus}
        rows = await self.db.execute(
            select(Application.status, func.count(Application.id))
            .where(*filters)
            .group_by(Application.status)
        )
        for status, count in rows.all():
            status_counts[status] = int(count)

        now = datetime.now(timezone.utc)
        overdue = (
            await self.db.execute(
                select(func.count(Application.id)).where(
                    *filters,
                    Application.status.in_(_ACTIVE_APPLICATION_STATUSES),
                    Application.assessment_deadline.is_not(None),
                    Application.assessment_deadline < now,
                )
            )
        ).scalar_one()

        bucket = bucket_for(period)
        activity_rows = await self.db.execute(
            select(
                func.date_trunc(bucket, Application.created_at).label("date"),
                func.count(Application.id).label("count"),
            )
            .where(*filters)
            .group_by("date")
            .order_by("date")
        )
        activity_by_date = {row.date.date(): int(row.count) for row in activity_rows}

        # GROUP BY only returns buckets that actually had an application, so
        # a quiet window with activity on just a couple of days would
        # otherwise come back as 2 sparse points instead of one per real
        # bucket — a chart with no zero baseline for quiet buckets, which
        # reads as broken rather than as "nothing happened here." Zero-fill
        # the requested window ("yearly" has no lower bound to enumerate
        # years from, so it stays sparse like before).
        if period == "yearly":
            application_activity = [
                {"date": d, "count": c} for d, c in sorted(activity_by_date.items())
            ]
        else:
            start_date = period_start(period, now).date()
            application_activity = [
                {"date": d, "count": activity_by_date.get(d, 0)}
                for d in bucket_starts(start_date, now.date(), bucket)
            ]

        return {
            "total_applications": total,
            "unique_applicants": int(row.unique_applicants),
            "active_candidates": int(row.active_candidates),
            "hires": hires,
            "hire_conversion_rate": rate(hires, total),
            "overdue_assessments": int(overdue),
            "by_status": [
                {"key": status.value, "count": status_counts[status.value]}
                for status in ApplicationStatus
            ],
            "application_activity": application_activity,
        }

    async def _roles(self, *, filters: list, position_id: uuid.UUID | None) -> dict:
        # Portfolio counts are all-time and unaffected by the period selector —
        # they describe the job-post inventory, not activity.
        portfolio = (
            await self.db.execute(
                select(
                    func.count(JobPost.id),
                    func.coalesce(
                        func.sum(case((JobPost.status == "published", 1), else_=0)),
                        0,
                    ),
                    func.coalesce(
                        func.sum(case((JobPost.status == "draft", 1), else_=0)),
                        0,
                    ),
                )
            )
        ).one()

        application_counts = (
            select(
                Application.job_post_id.label("job_post_id"),
                func.count(Application.id).label("application_count"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                Application.status.in_(_ACTIVE_APPLICATION_STATUSES),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("active_candidates"),
                func.coalesce(
                    func.sum(
                        case(
                            (Application.status == ApplicationStatus.SUCCESS.value, 1),
                            else_=0,
                        )
                    ),
                    0,
                ).label("hires"),
            )
            .where(*filters)
            .group_by(Application.job_post_id)
            .subquery()
        )
        count_column = func.coalesce(application_counts.c.application_count, 0)
        query = (
            select(
                JobPost.id,
                JobPost.job_title,
                JobPost.status,
                Position.title.label("position_title"),
                CompanyAddress.label.label("location_label"),
                count_column.label("application_count"),
                func.coalesce(application_counts.c.active_candidates, 0).label(
                    "active_candidates"
                ),
                func.coalesce(application_counts.c.hires, 0).label("hires"),
            )
            .join(Position, Position.id == JobPost.position_id)
            .join(CompanyAddress, CompanyAddress.id == JobPost.company_address_id)
            .outerjoin(
                application_counts,
                application_counts.c.job_post_id == JobPost.id,
            )
            .order_by(count_column.desc(), JobPost.job_title.asc())
        )
        if position_id is not None:
            # Scoped view: every job post for this position.
            query = query.where(JobPost.position_id == position_id)
        else:
            # The leaderboard only lists roles with activity in the period.
            query = query.where(count_column > 0).limit(_ROLE_LIMIT)

        rows = (await self.db.execute(query)).all()
        roles = [
            {
                "id": row.id,
                "job_title": row.job_title,
                "status": row.status,
                "position_title": row.position_title,
                "location_label": row.location_label,
                "application_count": int(row.application_count),
                "active_candidates": int(row.active_candidates),
                "hires": int(row.hires),
                "hire_conversion_rate": rate(
                    int(row.hires), int(row.application_count)
                ),
            }
            for row in rows
        ]

        # Applications rolled up by *position* (the reusable job title behind
        # one or more postings) — "which kind of role attracts the most people".
        position_rows = (
            await self.db.execute(
                select(
                    Position.id,
                    Position.title,
                    func.count(func.distinct(Application.job_post_id)).label(
                        "job_post_count"
                    ),
                    func.count(Application.id).label("application_count"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    Application.status.in_(
                                        _ACTIVE_APPLICATION_STATUSES
                                    ),
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("active_candidates"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    Application.status
                                    == ApplicationStatus.SUCCESS.value,
                                    1,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("hires"),
                )
                .select_from(Application)
                .join(JobPost, JobPost.id == Application.job_post_id)
                .join(Position, Position.id == JobPost.position_id)
                .where(*filters)
                .group_by(Position.id, Position.title)
                .order_by(func.count(Application.id).desc(), Position.title.asc())
                .limit(_ROLE_LIMIT)
            )
        ).all()
        positions = [
            {
                "id": row.id,
                "position_title": row.title,
                "job_post_count": int(row.job_post_count),
                "application_count": int(row.application_count),
                "active_candidates": int(row.active_candidates),
                "hires": int(row.hires),
                "hire_conversion_rate": rate(
                    int(row.hires), int(row.application_count)
                ),
            }
            for row in position_rows
        ]

        return {
            "total_job_posts": int(portfolio[0]),
            "published_job_posts": int(portfolio[1]),
            "draft_job_posts": int(portfolio[2]),
            "roles": roles,
            "positions": positions,
        }

    async def _assessments(self, *, filters: list) -> dict:
        template_rows = await self.db.execute(
            select(
                AssessmentAttempt.template_type,
                func.count(AssessmentAttempt.id).label("attempts"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                AssessmentAttempt.status
                                == AttemptStatus.NOT_STARTED.value,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("not_started"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                AssessmentAttempt.status
                                == AttemptStatus.IN_PROGRESS.value,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("in_progress"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                AssessmentAttempt.status
                                == AttemptStatus.COMPLETED.value,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("completed"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                AssessmentAttempt.status == AttemptStatus.EXPIRED.value,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("expired"),
                func.avg(
                    case(
                        (
                            and_(
                                AssessmentAttempt.started_at.is_not(None),
                                AssessmentAttempt.completed_at.is_not(None),
                            ),
                            func.extract(
                                "epoch",
                                AssessmentAttempt.completed_at
                                - AssessmentAttempt.started_at,
                            ),
                        ),
                        else_=None,
                    )
                ).label("average_seconds"),
            )
            .join(Application, Application.id == AssessmentAttempt.application_id)
            .where(*filters)
            .group_by(AssessmentAttempt.template_type)
        )
        by_template = {row.template_type: row for row in template_rows}
        templates = []
        for template_type in TemplateType:
            row = by_template.get(template_type.value)
            attempts = int(row.attempts) if row else 0
            not_started = int(row.not_started) if row else 0
            completed = int(row.completed) if row else 0
            started = attempts - not_started
            average_seconds = (
                float(row.average_seconds) if row and row.average_seconds else None
            )
            average_minutes = (
                round(average_seconds / 60, 1) if average_seconds is not None else None
            )
            templates.append(
                {
                    "template_type": template_type.value,
                    "attempts": attempts,
                    "not_started": not_started,
                    "in_progress": int(row.in_progress) if row else 0,
                    "completed": completed,
                    "expired": int(row.expired) if row else 0,
                    # Of attempts the candidate actually started.
                    "completion_rate": rate(completed, started),
                    "average_completion_minutes": average_minutes,
                }
            )

        reopens = (
            await self.db.execute(
                select(func.count(AssessmentAttemptReopen.id))
                .join(
                    AssessmentAttempt,
                    AssessmentAttempt.id == AssessmentAttemptReopen.attempt_id,
                )
                .join(Application, Application.id == AssessmentAttempt.application_id)
                .where(*filters)
            )
        ).scalar_one()

        total_attempts = sum(t["attempts"] for t in templates)
        not_started = sum(t["not_started"] for t in templates)
        completed_attempts = sum(t["completed"] for t in templates)
        expired_attempts = sum(t["expired"] for t in templates)
        started_attempts = total_attempts - not_started
        average_duration = weighted_average(
            [
                (t["average_completion_minutes"], t["completed"])
                for t in templates
                if t["average_completion_minutes"] is not None
            ]
        )
        return {
            "total_attempts": total_attempts,
            "started_attempts": started_attempts,
            "completed_attempts": completed_attempts,
            "expired_attempts": expired_attempts,
            # "of all issued attempts" (includes not-yet-started).
            "completion_rate": rate(completed_attempts, total_attempts),
            # "of attempts the candidate actually started".
            "started_completion_rate": rate(completed_attempts, started_attempts),
            "average_completion_minutes": average_duration,
            "reopen_count": int(reopens),
            "templates": templates,
        }

    async def _evaluations(
        self,
        *,
        period: str,
        position_id: uuid.UUID | None,
    ) -> dict:
        # Current-state metrics: the latest evaluation of every application in
        # scope, regardless of when it was imported. Only the activity chart is
        # period-scoped — the one "recent activity" view.
        scope_filters: list = []
        if position_id is not None:
            scope_filters.append(
                Application.job_post_id.in_(
                    select(JobPost.id).where(JobPost.position_id == position_id)
                )
            )

        scoped_applications = (
            await self.db.execute(
                select(func.count(Application.id)).where(*scope_filters)
            )
        ).scalar_one()

        ranked_evaluations = (
            select(
                ApplicationEvaluation.id,
                ApplicationEvaluation.application_id,
                ApplicationEvaluation.recommendation,
                ApplicationEvaluation.fit_score,
                func.row_number()
                .over(
                    partition_by=ApplicationEvaluation.application_id,
                    order_by=(
                        ApplicationEvaluation.created_at.desc(),
                        ApplicationEvaluation.id.desc(),
                    ),
                )
                .label("rank"),
            )
            .join(Application, Application.id == ApplicationEvaluation.application_id)
            .where(*scope_filters)
            .subquery()
        )
        latest_evaluations = (
            select(ranked_evaluations).where(ranked_evaluations.c.rank == 1).subquery()
        )
        evaluations = (await self.db.execute(select(latest_evaluations))).all()
        recommendations = {"advance": 0, "hold": 0, "reject": 0}
        fit_scores: list[int] = []
        for evaluation in evaluations:
            if evaluation.recommendation in recommendations:
                recommendations[evaluation.recommendation] += 1
            if evaluation.fit_score is not None:
                fit_scores.append(int(evaluation.fit_score))

        dimension_rows = await self.db.execute(
            select(
                ApplicationEvaluationScore.category,
                ApplicationEvaluationScore.dimension,
                ApplicationEvaluationScore.rating,
                func.count(ApplicationEvaluationScore.id).label("count"),
            )
            .join(
                latest_evaluations,
                latest_evaluations.c.id == ApplicationEvaluationScore.evaluation_id,
            )
            .group_by(
                ApplicationEvaluationScore.category,
                ApplicationEvaluationScore.dimension,
                ApplicationEvaluationScore.rating,
            )
            .order_by(
                ApplicationEvaluationScore.category,
                ApplicationEvaluationScore.dimension,
            )
        )
        dimensions: dict[tuple[str, str], dict] = {}
        for row in dimension_rows:
            key = (row.category, row.dimension)
            dimensions.setdefault(
                key,
                {
                    "category": row.category,
                    "dimension": row.dimension,
                    "strong": 0,
                    "qualified": 0,
                    "below_bar": 0,
                    "na": 0,
                },
            )[row.rating] = int(row.count)

        now = datetime.now(timezone.utc)
        activity_filters: list = list(scope_filters)
        start = period_start(period, now)
        if start is not None:
            activity_filters.append(ApplicationEvaluation.created_at >= start)
        bucket = bucket_for(period)
        activity_rows = await self.db.execute(
            select(
                func.date_trunc(bucket, ApplicationEvaluation.created_at).label("date"),
                func.count(ApplicationEvaluation.id).label("count"),
            )
            .join(Application, Application.id == ApplicationEvaluation.application_id)
            .where(*activity_filters)
            .group_by("date")
            .order_by("date")
        )
        evaluation_activity_by_date = {
            row.date.date(): int(row.count) for row in activity_rows
        }
        # Same zero-fill reasoning as application_activity in _hiring above.
        if period == "yearly":
            evaluation_activity = [
                {"date": d, "count": c}
                for d, c in sorted(evaluation_activity_by_date.items())
            ]
        else:
            evaluation_activity = [
                {"date": d, "count": evaluation_activity_by_date.get(d, 0)}
                for d in bucket_starts(start.date(), now.date(), bucket)
            ]

        bands = fit_score_bands(fit_scores)
        return {
            "evaluated_applications": len(evaluations),
            # Coverage is all-time: "of every application in scope, how many
            # have a current evaluation" — a stable number, not a period rate.
            "evaluation_coverage_rate": rate(
                len(evaluations), int(scoped_applications)
            ),
            "average_fit_score": (
                round(sum(fit_scores) / len(fit_scores), 1) if fit_scores else None
            ),
            "recommendations": [
                {"key": key, "count": value} for key, value in recommendations.items()
            ],
            "evaluation_activity": evaluation_activity,
            "fit_score_bands": [
                {"key": key, "count": value} for key, value in bands.items()
            ],
            "score_dimensions": list(dimensions.values()),
        }

    async def location_counts(
        self, *, position_id: uuid.UUID | None
    ) -> list[dict]:
        """Latest evaluation's `location` per application in scope, tallied —
        for the analytics locations graph/heatmap. All-time current-state,
        same coverage semantics as the rest of _evaluations (not period-
        scoped — this is "where are they now", not a recent-activity view)."""
        scope_filters: list = []
        if position_id is not None:
            scope_filters.append(
                Application.job_post_id.in_(
                    select(JobPost.id).where(JobPost.position_id == position_id)
                )
            )
        ranked = (
            select(
                ApplicationEvaluation.application_id,
                ApplicationEvaluation.location,
                func.row_number()
                .over(
                    partition_by=ApplicationEvaluation.application_id,
                    order_by=(
                        ApplicationEvaluation.created_at.desc(),
                        ApplicationEvaluation.id.desc(),
                    ),
                )
                .label("rank"),
            )
            .join(Application, Application.id == ApplicationEvaluation.application_id)
            .where(*scope_filters)
            .subquery()
        )
        rows = await self.db.execute(
            select(
                ranked.c.location, func.count(ranked.c.application_id).label("count")
            )
            .where(ranked.c.rank == 1, ranked.c.location.is_not(None))
            .group_by(ranked.c.location)
            .order_by(func.count(ranked.c.application_id).desc())
        )
        return [{"key": row.location, "count": int(row.count)} for row in rows]

    async def job_post_reports(
        self, *, position_id: uuid.UUID | None
    ) -> list[dict]:
        """One row per job post — lifetime performance for the recruitment
        report. Not period-scoped: this is "how has this posting done since
        it went live," independent of the dashboard's period selector."""
        filters: list = []
        if position_id is not None:
            filters.append(JobPost.position_id == position_id)

        posts = (
            await self.db.execute(
                select(
                    JobPost.id,
                    JobPost.job_title,
                    JobPost.status,
                    JobPost.published_at,
                    JobPost.closed_at,
                    JobPost.expires_at,
                ).where(*filters)
            )
        ).all()
        if not posts:
            return []
        post_ids = [p.id for p in posts]

        status_rows = await self.db.execute(
            select(
                Application.job_post_id,
                Application.status,
                func.count(Application.id),
            )
            .where(Application.job_post_id.in_(post_ids))
            .group_by(Application.job_post_id, Application.status)
        )
        by_post_status: dict[uuid.UUID, dict[str, int]] = {
            post_id: {} for post_id in post_ids
        }
        for job_post_id, status, count in status_rows:
            by_post_status[job_post_id][status] = int(count)

        # Latest evaluation's fit_score per application (review pattern
        # shared with location_counts above), then avg/max per job post.
        ranked_evals = (
            select(
                ApplicationEvaluation.application_id,
                ApplicationEvaluation.fit_score,
                func.row_number()
                .over(
                    partition_by=ApplicationEvaluation.application_id,
                    order_by=(
                        ApplicationEvaluation.created_at.desc(),
                        ApplicationEvaluation.id.desc(),
                    ),
                )
                .label("rank"),
            )
            .join(
                Application, Application.id == ApplicationEvaluation.application_id
            )
            .where(Application.job_post_id.in_(post_ids))
            .subquery()
        )
        score_rows = await self.db.execute(
            select(
                Application.job_post_id,
                func.avg(ranked_evals.c.fit_score),
                func.max(ranked_evals.c.fit_score),
            )
            .join(ranked_evals, ranked_evals.c.application_id == Application.id)
            .where(ranked_evals.c.rank == 1, ranked_evals.c.fit_score.is_not(None))
            .group_by(Application.job_post_id)
        )
        scores_by_post: dict[uuid.UUID, tuple[float | None, int | None]] = {
            row[0]: (
                float(row[1]) if row[1] is not None else None,
                int(row[2]) if row[2] is not None else None,
            )
            for row in score_rows
        }

        # Recurring applicants: of this post's applicants, how many have
        # applied more than once anywhere in the system (this post included).
        applicant_totals = (
            select(
                Application.applicant_id,
                func.count(Application.id).label("total_applications"),
            )
            .group_by(Application.applicant_id)
            .subquery()
        )
        recurring_rows = await self.db.execute(
            select(
                Application.job_post_id,
                func.count(func.distinct(Application.applicant_id)),
            )
            .join(
                applicant_totals,
                applicant_totals.c.applicant_id == Application.applicant_id,
            )
            .where(
                Application.job_post_id.in_(post_ids),
                applicant_totals.c.total_applications > 1,
            )
            .group_by(Application.job_post_id)
        )
        recurring_by_post = {row[0]: int(row[1]) for row in recurring_rows}

        # Engagement: applications that actually started at least one
        # assessment (as opposed to applying and never opening it) — a
        # behavioral signal distinct from `screened`, which tracks pipeline
        # stage rather than candidate activity.
        engaged_rows = await self.db.execute(
            select(
                Application.job_post_id,
                func.count(func.distinct(Application.id)),
            )
            .join(
                AssessmentAttempt, AssessmentAttempt.application_id == Application.id
            )
            .where(
                Application.job_post_id.in_(post_ids),
                AssessmentAttempt.status != AttemptStatus.NOT_STARTED.value,
            )
            .group_by(Application.job_post_id)
        )
        engaged_by_post = {row[0]: int(row[1]) for row in engaged_rows}

        now = datetime.now(timezone.utc)
        reports = []
        for post in posts:
            statuses = by_post_status.get(post.id, {})
            applied = sum(statuses.values())
            # "Screened" = moved beyond the raw applied state at all
            # (prescreening, interview, denied, success, failed, or
            # disqualified) — a coarse "did anything happen yet" signal.
            screened = applied - statuses.get(ApplicationStatus.APPLIED.value, 0)
            passed = statuses.get(
                ApplicationStatus.INTERVIEW.value, 0
            ) + statuses.get(ApplicationStatus.SUCCESS.value, 0)
            accepted = statuses.get(ApplicationStatus.SUCCESS.value, 0)
            rejected = (
                statuses.get(ApplicationStatus.DENIED.value, 0)
                + statuses.get(ApplicationStatus.FAILED.value, 0)
                + statuses.get(ApplicationStatus.DISQUALIFIED.value, 0)
            )
            avg_score, max_score = scores_by_post.get(post.id, (None, None))
            engaged = engaged_by_post.get(post.id, 0)

            posting_duration_days = None
            if post.published_at is not None:
                posting_duration_days = (
                    (post.closed_at or now) - post.published_at
                ).days

            reports.append(
                {
                    "id": post.id,
                    "job_title": post.job_title,
                    "status": post.status,
                    "published_at": post.published_at,
                    "closed_at": post.closed_at,
                    "expires_at": post.expires_at,
                    "applied": applied,
                    "screened": screened,
                    "passed": passed,
                    "rejected": rejected,
                    "accepted": accepted,
                    "average_score": (
                        round(avg_score, 1) if avg_score is not None else None
                    ),
                    "highest_score": max_score,
                    "recurring_applicants": recurring_by_post.get(post.id, 0),
                    "turnout": applied,
                    "engagement_rate": rate(engaged, applied),
                    "posting_duration_days": posting_duration_days,
                    "recommendation": _recommend(
                        status=post.status,
                        applied=applied,
                        screened=screened,
                        passed=passed,
                        accepted=accepted,
                        avg_score=avg_score,
                        posting_duration_days=posting_duration_days,
                    ),
                }
            )
        return reports

    async def recruitment_insights(self, *, position_id: uuid.UUID | None) -> dict:
        """The recruitment report's "Key Recruitment Insights" summary —
        rankings and totals computed from job_post_reports(), so the
        frontend never re-derives this business logic (which posting is
        "strongest," which recommendation counts as "strongest") itself."""
        reports = await self.job_post_reports(position_id=position_id)

        def _ranked(items: list[dict]) -> list[dict]:
            return [
                {"id": r["id"], "job_title": r["job_title"], "value": r["_value"]}
                for r in items
            ]

        with_applied = [
            dict(r, _value=r["turnout"]) for r in reports if r["applied"] > 0
        ]
        top_turnout = _ranked(
            sorted(with_applied, key=lambda r: r["_value"], reverse=True)[:5]
        )

        with_engagement = [
            dict(r, _value=r["engagement_rate"])
            for r in reports
            if r["applied"] > 0
        ]
        top_engagement = _ranked(
            sorted(with_engagement, key=lambda r: r["_value"], reverse=True)[:5]
        )

        with_duration = [
            dict(r, _value=r["posting_duration_days"])
            for r in reports
            if r["posting_duration_days"] is not None
        ]
        top_duration = _ranked(
            sorted(with_duration, key=lambda r: r["_value"], reverse=True)[:5]
        )

        with_recommendation = [r for r in reports if r["recommendation"]]
        strongest_recommendation = (
            next(
                (
                    r
                    for r in with_recommendation
                    if r["recommendation"]
                    == "Close the posting after sufficient qualified "
                    "applicants are identified"
                ),
                None,
            )
            or next(
                (
                    r
                    for r in with_recommendation
                    if r["recommendation"] == "Prioritize high-scoring candidates"
                ),
                None,
            )
            or (with_recommendation[0] if with_recommendation else None)
        )
        recommendation_counts: dict[str, int] = {}
        for r in with_recommendation:
            recommendation_counts[r["recommendation"]] = (
                recommendation_counts.get(r["recommendation"], 0) + 1
            )
        recommendation_distribution = sorted(
            (
                {"recommendation": rec, "count": count}
                for rec, count in recommendation_counts.items()
            ),
            key=lambda row: row["count"],
            reverse=True,
        )

        total_applied = sum(r["applied"] for r in reports)
        total_screened = sum(r["screened"] for r in reports)
        total_passed = sum(r["passed"] for r in reports)
        total_recurring = sum(r["recurring_applicants"] for r in reports)

        return {
            "top_turnout": top_turnout,
            "top_engagement": top_engagement,
            "top_duration": top_duration,
            "strongest_recommendation": (
                {
                    "id": strongest_recommendation["id"],
                    "job_title": strongest_recommendation["job_title"],
                    "recommendation": strongest_recommendation["recommendation"],
                }
                if strongest_recommendation
                else None
            ),
            "recommendation_distribution": recommendation_distribution,
            "recurring_applicants_total": total_recurring,
            "total_applied": total_applied,
            "total_screened": total_screened,
            "total_passed": total_passed,
            "candidates_passed_rate": rate(total_passed, total_applied),
        }

    async def recurring_applicants(
        self, *, position_id: uuid.UUID | None
    ) -> list[dict]:
        """Applicants with more than one application anywhere in the system —
        the detail behind the recruitment report's "recurring applicants"
        insight card. When `position_id` is set, scoped to applicants who
        applied to at least one job post under that position (their full
        application history is still shown, not just that position's)."""
        applicant_totals = (
            select(
                Application.applicant_id,
                func.count(Application.id).label("total_applications"),
            )
            .group_by(Application.applicant_id)
            .having(func.count(Application.id) > 1)
            .subquery()
        )

        applicant_ids_query = select(applicant_totals.c.applicant_id)
        if position_id is not None:
            applicant_ids_query = applicant_ids_query.where(
                applicant_totals.c.applicant_id.in_(
                    select(Application.applicant_id)
                    .join(JobPost, JobPost.id == Application.job_post_id)
                    .where(JobPost.position_id == position_id)
                )
            )
        applicant_ids = (
            (await self.db.execute(applicant_ids_query)).scalars().all()
        )
        if not applicant_ids:
            return []

        users = (
            await self.db.execute(
                select(User.id, User.first_name, User.last_name, User.email).where(
                    User.id.in_(applicant_ids)
                )
            )
        ).all()

        app_rows = (
            await self.db.execute(
                select(
                    Application.applicant_id,
                    Application.job_post_id,
                    JobPost.job_title,
                    Application.status,
                    Application.created_at,
                )
                .join(JobPost, JobPost.id == Application.job_post_id)
                .where(Application.applicant_id.in_(applicant_ids))
                .order_by(Application.created_at.desc())
            )
        ).all()
        applications_by_applicant: dict[uuid.UUID, list[dict]] = {
            applicant_id: [] for applicant_id in applicant_ids
        }
        for applicant_id, job_post_id, job_title, status, created_at in app_rows:
            applications_by_applicant[applicant_id].append(
                {
                    "job_post_id": job_post_id,
                    "job_title": job_title,
                    "status": status,
                    "created_at": created_at,
                }
            )

        return sorted(
            (
                {
                    "applicant_id": user_id,
                    "name": f"{first_name} {last_name}",
                    "email": email,
                    "application_count": len(applications_by_applicant[user_id]),
                    "applications": applications_by_applicant[user_id],
                }
                for user_id, first_name, last_name, email in users
            ),
            key=lambda row: row["application_count"],
            reverse=True,
        )
