"""AI evaluation import + read side.

HR exports the evaluation pack (see export.py), runs it through an external
agent, then imports the agent's JSON here. Each import is stored as one
`ApplicationEvaluation` (+ normalised per-dimension `ApplicationEvaluationScore`
rows) so it can drive analytics later. The newest row per application is
"current".
"""

import csv
import io
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.domains.applications.models import (
    Application,
    ApplicationEvaluation,
    ApplicationEvaluationScore,
)
from app.domains.auth.models import User

# Canonical dimensions — the agent SHOULD use these, but unknown strings are
# still stored (analytics groups on whatever is there). Kept here so the
# export pack's schema file and this importer never drift.
RESUME_DIMENSIONS = [
    "relevant_work_experience",
    "industry_experience",
    "employment_gap",
    "tenure_stability",
    "career_progression",
    "job_hopping_risk",
    "educational_background",
    "certifications_licenses",
    "technical_skills_match",
]
ASSESSMENT_DIMENSIONS = ["pre_assessment", "culture_fit", "technical"]

Rating = Literal["strong", "qualified", "below_bar", "na"]
Recommendation = Literal["advance", "hold", "reject"]


class EvaluationScoreIn(BaseModel):
    dimension: str
    rating: Rating
    reason: str | None = None


def _drop_blank_scores(value: object) -> object:
    """Template stubs ship with rating="" — quietly drop unfilled rows rather
    than 422 the whole import."""
    if isinstance(value, list):
        return [
            v
            for v in value
            if not (isinstance(v, dict) and not str(v.get("rating") or "").strip())
        ]
    return value


class ApplicationEvaluationIn(BaseModel):
    application_id: uuid.UUID
    seniority_assessed: str | None = None
    fit_score: int | None = Field(default=None, ge=0, le=100)
    recommendation: Recommendation | None = None
    summary: str | None = None
    resume_scores: list[EvaluationScoreIn] = Field(default_factory=list)
    assessment_scores: list[EvaluationScoreIn] = Field(default_factory=list)

    @field_validator("seniority_assessed", "summary", "recommendation", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("resume_scores", "assessment_scores", mode="before")
    @classmethod
    def _prune_scores(cls, v: object) -> object:
        return _drop_blank_scores(v)


class EvaluationImportIn(BaseModel):
    job_post_id: uuid.UUID
    model: str | None = None
    rubric_version: str | None = None
    evaluations: list[ApplicationEvaluationIn]


class EvaluationImportResultOut(BaseModel):
    imported: int
    skipped: list[str] = Field(default_factory=list)


class EvaluationScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str
    dimension: str
    rating: str
    reason: str | None


class ApplicationEvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    recommendation: str | None
    fit_score: int | None
    seniority_assessed: str | None
    summary: str | None
    model: str | None
    rubric_version: str | None
    created_at: datetime
    scores: list[EvaluationScoreOut] = Field(default_factory=list)


class JobEvaluationRowOut(BaseModel):
    """One applicant's latest AI evaluation, for the Compare tab's
    side-by-side evaluation matrix."""

    application_id: uuid.UUID
    applicant_first_name: str
    applicant_last_name: str
    applicant_email: str
    evaluation: ApplicationEvaluationOut | None = None


class EvaluationService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def import_results(
        self, payload: EvaluationImportIn, *, imported_by_user_id: uuid.UUID
    ) -> EvaluationImportResultOut:
        if not payload.evaluations:
            raise ValidationError("No evaluations in payload")

        # Only accept applications that actually belong to this job post.
        result = await self.db.execute(
            select(Application.id).where(Application.job_post_id == payload.job_post_id)
        )
        valid_ids = {row[0] for row in result.all()}

        imported = 0
        skipped: list[str] = []
        for item in payload.evaluations:
            if item.application_id not in valid_ids:
                skipped.append(str(item.application_id))
                continue
            is_empty = (
                item.recommendation is None
                and item.fit_score is None
                and not item.resume_scores
                and not item.assessment_scores
                and not item.summary
            )
            if is_empty:
                skipped.append(str(item.application_id))
                continue

            evaluation = ApplicationEvaluation(
                id=uuid.uuid4(),
                application_id=item.application_id,
                imported_by_user_id=imported_by_user_id,
                recommendation=item.recommendation,
                fit_score=item.fit_score,
                seniority_assessed=item.seniority_assessed,
                summary=item.summary,
                model=payload.model,
                rubric_version=payload.rubric_version,
            )
            self.db.add(evaluation)
            await self.db.flush()

            for category, scores in (
                ("resume", item.resume_scores),
                ("assessment", item.assessment_scores),
            ):
                for score in scores:
                    self.db.add(
                        ApplicationEvaluationScore(
                            id=uuid.uuid4(),
                            evaluation_id=evaluation.id,
                            category=category,
                            dimension=score.dimension,
                            rating=score.rating,
                            reason=score.reason,
                        )
                    )
            imported += 1

        await self.db.commit()
        return EvaluationImportResultOut(imported=imported, skipped=skipped)

    async def _latest(self, application_id: uuid.UUID) -> ApplicationEvaluation | None:
        result = await self.db.execute(
            select(ApplicationEvaluation)
            .where(ApplicationEvaluation.application_id == application_id)
            .order_by(ApplicationEvaluation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_for_application(
        self, application_id: uuid.UUID
    ) -> ApplicationEvaluationOut:
        evaluation = await self._latest(application_id)
        if evaluation is None:
            raise NotFoundError(
                f"No evaluation imported for application '{application_id}'"
            )
        scores = await self.db.execute(
            select(ApplicationEvaluationScore).where(
                ApplicationEvaluationScore.evaluation_id == evaluation.id
            )
        )
        out = ApplicationEvaluationOut.model_validate(evaluation)
        out.scores = [
            EvaluationScoreOut.model_validate(s) for s in scores.scalars().all()
        ]
        return out

    async def latest_full_for_applications(
        self, application_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ApplicationEvaluationOut]:
        """Newest evaluation + its per-dimension scores for each application,
        batched (2 queries total)."""
        if not application_ids:
            return {}
        eval_rows = await self.db.execute(
            select(ApplicationEvaluation)
            .where(ApplicationEvaluation.application_id.in_(application_ids))
            .order_by(ApplicationEvaluation.created_at.desc())
        )
        latest: dict[uuid.UUID, ApplicationEvaluation] = {}
        for row in eval_rows.scalars().all():
            latest.setdefault(row.application_id, row)
        if not latest:
            return {}
        score_rows = await self.db.execute(
            select(ApplicationEvaluationScore).where(
                ApplicationEvaluationScore.evaluation_id.in_(
                    [e.id for e in latest.values()]
                )
            )
        )
        by_evaluation: dict[uuid.UUID, list[ApplicationEvaluationScore]] = defaultdict(
            list
        )
        for score in score_rows.scalars().all():
            by_evaluation[score.evaluation_id].append(score)

        out: dict[uuid.UUID, ApplicationEvaluationOut] = {}
        for app_id, evaluation in latest.items():
            dto = ApplicationEvaluationOut.model_validate(evaluation)
            dto.scores = [
                EvaluationScoreOut.model_validate(s)
                for s in by_evaluation.get(evaluation.id, [])
            ]
            out[app_id] = dto
        return out

    async def latest_summaries_for_applications(
        self, application_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict]:
        """`{application_id: {recommendation, fit_score}}` for the newest
        evaluation of each — for the Compare scorecard column."""
        if not application_ids:
            return {}
        result = await self.db.execute(
            select(ApplicationEvaluation)
            .where(ApplicationEvaluation.application_id.in_(application_ids))
            .order_by(ApplicationEvaluation.created_at.desc())
        )
        out: dict[uuid.UUID, dict] = {}
        for row in result.scalars().all():
            if row.application_id in out:
                continue  # first seen = newest (ordered desc)
            out[row.application_id] = {
                "recommendation": row.recommendation,
                "fit_score": row.fit_score,
            }
        return out

    async def evaluation_csv(self, job_post_id: uuid.UUID) -> str:
        """Flat CSV of the latest evaluation per applicant for one job post —
        one row per applicant, one column per dimension rating. For analytics /
        spreadsheets."""
        app_rows = (
            await self.db.execute(
                select(
                    Application.id,
                    User.first_name,
                    User.last_name,
                    User.email,
                    Application.status,
                )
                .join(User, User.id == Application.applicant_id)
                .where(Application.job_post_id == job_post_id)
                .order_by(User.first_name, User.last_name)
            )
        ).all()
        app_ids = [r[0] for r in app_rows]

        latest: dict[uuid.UUID, ApplicationEvaluation] = {}
        if app_ids:
            evals = await self.db.execute(
                select(ApplicationEvaluation)
                .where(ApplicationEvaluation.application_id.in_(app_ids))
                .order_by(ApplicationEvaluation.created_at.desc())
            )
            for e in evals.scalars().all():
                latest.setdefault(e.application_id, e)

        scores_by_eval: dict[uuid.UUID, dict[tuple[str, str], tuple[str, str]]] = {}
        if latest:
            score_rows = await self.db.execute(
                select(ApplicationEvaluationScore).where(
                    ApplicationEvaluationScore.evaluation_id.in_(
                        [e.id for e in latest.values()]
                    )
                )
            )
            for s in score_rows.scalars().all():
                scores_by_eval.setdefault(s.evaluation_id, {})[
                    (s.category, s.dimension)
                ] = (s.rating, s.reason or "")

        dimensions = [("resume", d) for d in RESUME_DIMENSIONS] + [
            ("assessment", d) for d in ASSESSMENT_DIMENSIONS
        ]
        dimension_headers: list[str] = []
        for category, dimension in dimensions:
            dimension_headers += [
                f"{category}__{dimension}",
                f"{category}__{dimension}__reason",
            ]
        header = [
            "application_id",
            "applicant_name",
            "applicant_email",
            "pipeline_status",
            "recommendation",
            "fit_score",
            "seniority_assessed",
            "model",
            "rubric_version",
            "evaluated_at",
            *dimension_headers,
        ]

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        for app_id, first, last, email, status in app_rows:
            evaluation = latest.get(app_id)
            base = [str(app_id), f"{first} {last}", email, status]
            if evaluation is None:
                writer.writerow(base + [""] * (len(header) - len(base)))
                continue
            smap = scores_by_eval.get(evaluation.id, {})
            dimension_values: list[str] = []
            for key in dimensions:
                rating, reason = smap.get(key, ("", ""))
                dimension_values += [rating, reason]
            writer.writerow(
                [
                    *base,
                    evaluation.recommendation or "",
                    "" if evaluation.fit_score is None else evaluation.fit_score,
                    evaluation.seniority_assessed or "",
                    evaluation.model or "",
                    evaluation.rubric_version or "",
                    evaluation.created_at.isoformat(),
                    *dimension_values,
                ]
            )
        return buffer.getvalue()
