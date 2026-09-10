import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.aggregation import (
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
from app.domains.company_addresses.models import CompanyAddress

# analytics is the one read-only cross-domain reporting layer: it queries other
# domains' models directly (here, the evaluations domain) rather than going
# through their repositories/services. It owns no write paths, so this stays
# consistent with how it already reaches into job_posts / assessments / etc.
from app.domains.evaluations.models import (
    ApplicationEvaluation,
    ApplicationEvaluationScore,
)
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

        bucket = "month" if period == "all" else "day"
        activity_rows = await self.db.execute(
            select(
                func.date_trunc(bucket, Application.created_at).label("date"),
                func.count(Application.id).label("count"),
            )
            .where(*filters)
            .group_by("date")
            .order_by("date")
        )

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
            "application_activity": [
                {"date": row.date.date(), "count": int(row.count)}
                for row in activity_rows
            ],
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
                    order_by=ApplicationEvaluation.created_at.desc(),
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

        activity_filters: list = list(scope_filters)
        start = period_start(period)
        if start is not None:
            activity_filters.append(ApplicationEvaluation.created_at >= start)
        bucket = "month" if period == "all" else "day"
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
            "evaluation_activity": [
                {"date": row.date.date(), "count": int(row.count)}
                for row in activity_rows
            ],
            "fit_score_bands": [
                {"key": key, "count": value} for key, value in bands.items()
            ],
            "score_dimensions": list(dimensions.values()),
        }
