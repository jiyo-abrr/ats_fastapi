"""Persistence for the import/read side of `evaluations/` (review F07) —
`ApplicationEvaluation` + `ApplicationEvaluationScore`. Stages changes only;
callers commit via `UnitOfWork`, same as every other conforming domain.

The application-rows-per-job-post query joins `applications`/`users` (cross-
domain) the same way `InterviewRepository`'s reporting queries and
`ApplicationRepository.list_for_review` do — a sanctioned projection read
(`docs/architecture.md`), not something F07 asks to change.
"""

import uuid
from collections import defaultdict

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.applications.models import Application
from app.domains.auth.models import User
from app.domains.evaluations import entities
from app.domains.evaluations.models import (
    ApplicationEvaluation as ApplicationEvaluationModel,
)
from app.domains.evaluations.models import (
    ApplicationEvaluationScore as ApplicationEvaluationScoreModel,
)


class EvaluationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _score_to_entity(
        obj: ApplicationEvaluationScoreModel,
    ) -> entities.EvaluationScore:
        return entities.EvaluationScore(
            id=obj.id,
            evaluation_id=obj.evaluation_id,
            category=obj.category,
            dimension=obj.dimension,
            rating=obj.rating,
            reason=obj.reason,
        )

    def _to_entity(
        self,
        obj: ApplicationEvaluationModel,
        scores: list[ApplicationEvaluationScoreModel] | None = None,
    ) -> entities.ApplicationEvaluation:
        return entities.ApplicationEvaluation(
            id=obj.id,
            application_id=obj.application_id,
            imported_by_user_id=obj.imported_by_user_id,
            recommendation=obj.recommendation,
            fit_score=obj.fit_score,
            seniority_assessed=obj.seniority_assessed,
            summary=obj.summary,
            model=obj.model,
            rubric_version=obj.rubric_version,
            created_at=obj.created_at,
            scores=[self._score_to_entity(s) for s in (scores or [])],
        )

    async def valid_application_ids(self, job_post_id: uuid.UUID) -> set[uuid.UUID]:
        result = await self.db.execute(
            select(Application.id).where(Application.job_post_id == job_post_id)
        )
        return {row[0] for row in result.all()}

    async def add(self, evaluation: entities.ApplicationEvaluation) -> None:
        """Stages the evaluation row, flushes (no `relationship()` across
        this FK, so the session's automatic insert-ordering can't infer it —
        same reason `JobPostService.create()` flushes before staging tags;
        see CLAUDE.md), then stages its score rows."""
        self.db.add(
            ApplicationEvaluationModel(
                id=evaluation.id,
                application_id=evaluation.application_id,
                imported_by_user_id=evaluation.imported_by_user_id,
                recommendation=evaluation.recommendation,
                fit_score=evaluation.fit_score,
                seniority_assessed=evaluation.seniority_assessed,
                summary=evaluation.summary,
                model=evaluation.model,
                rubric_version=evaluation.rubric_version,
            )
        )
        await self.db.flush()
        for score in evaluation.scores:
            self.db.add(
                ApplicationEvaluationScoreModel(
                    id=score.id,
                    evaluation_id=evaluation.id,
                    category=score.category,
                    dimension=score.dimension,
                    rating=score.rating,
                    reason=score.reason,
                )
            )

    async def get_latest(
        self, application_id: uuid.UUID
    ) -> entities.ApplicationEvaluation | None:
        obj = (
            await self.db.execute(
                select(ApplicationEvaluationModel)
                .where(ApplicationEvaluationModel.application_id == application_id)
                .order_by(
                    ApplicationEvaluationModel.created_at.desc(),
                    ApplicationEvaluationModel.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if obj is None:
            return None
        scores = (
            (
                await self.db.execute(
                    select(ApplicationEvaluationScoreModel).where(
                        ApplicationEvaluationScoreModel.evaluation_id == obj.id
                    )
                )
            )
            .scalars()
            .all()
        )
        return self._to_entity(obj, list(scores))

    async def latest_full_for_applications(
        self, application_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, entities.ApplicationEvaluation]:
        """Newest evaluation + its per-dimension scores for each application,
        batched (2 queries total)."""
        if not application_ids:
            return {}
        eval_rows = await self.db.execute(
            select(ApplicationEvaluationModel)
            .where(ApplicationEvaluationModel.application_id.in_(application_ids))
            .order_by(
                ApplicationEvaluationModel.created_at.desc(),
                ApplicationEvaluationModel.id.desc(),
            )
        )
        latest: dict[uuid.UUID, ApplicationEvaluationModel] = {}
        for row in eval_rows.scalars().all():
            latest.setdefault(row.application_id, row)
        if not latest:
            return {}
        score_rows = await self.db.execute(
            select(ApplicationEvaluationScoreModel).where(
                ApplicationEvaluationScoreModel.evaluation_id.in_(
                    [e.id for e in latest.values()]
                )
            )
        )
        by_evaluation: dict[uuid.UUID, list[ApplicationEvaluationScoreModel]] = (
            defaultdict(list)
        )
        for score in score_rows.scalars().all():
            by_evaluation[score.evaluation_id].append(score)

        return {
            app_id: self._to_entity(evaluation, by_evaluation.get(evaluation.id, []))
            for app_id, evaluation in latest.items()
        }

    async def latest_summaries_for_applications(
        self, application_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict]:
        """`{application_id: {recommendation, fit_score}}` for the newest
        evaluation of each — for the Compare scorecard column."""
        if not application_ids:
            return {}
        result = await self.db.execute(
            select(ApplicationEvaluationModel)
            .where(ApplicationEvaluationModel.application_id.in_(application_ids))
            .order_by(
                ApplicationEvaluationModel.created_at.desc(),
                ApplicationEvaluationModel.id.desc(),
            )
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

    async def application_rows_for_job_post(self, job_post_id: uuid.UUID) -> list[Row]:
        """`(id, first_name, last_name, email, status)` per applicant, for the
        flat evaluations CSV export."""
        result = await self.db.execute(
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
        return list(result.all())
