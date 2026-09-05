import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.domains.assessments import entities
from app.domains.assessments.enums import TemplateType
from app.domains.assessments.models import AssessmentAnswer as AssessmentAnswerModel
from app.domains.assessments.models import AssessmentAttempt as AssessmentAttemptModel
from app.domains.assessments.models import (
    AssessmentAttemptReopen as AssessmentAttemptReopenModel,
)
from app.domains.culture_fit_templates.models import (
    CultureFitTemplate as CultureFitTemplateModel,
)
from app.domains.pre_assessment_templates.models import (
    PreAssessmentTemplate as PreAssessmentTemplateModel,
)
from app.domains.technical_assessment_templates.models import (
    TechnicalAssessmentTemplate as TechnicalAssessmentTemplateModel,
)

_TEMPLATE_MODEL_BY_TYPE = {
    TemplateType.PRE_ASSESSMENT: PreAssessmentTemplateModel,
    TemplateType.CULTURE_FIT: CultureFitTemplateModel,
    TemplateType.TECHNICAL: TechnicalAssessmentTemplateModel,
}


class AssessmentAttemptRepository(
    BaseRepository[AssessmentAttemptModel, entities.AssessmentAttempt, uuid.UUID]
):
    model = AssessmentAttemptModel

    async def _to_entity(
        self, obj: AssessmentAttemptModel
    ) -> entities.AssessmentAttempt:
        return entities.AssessmentAttempt(
            id=obj.id,
            application_id=obj.application_id,
            template_type=obj.template_type,
            template_id=obj.template_id,
            status=obj.status,
            started_at=obj.started_at,
            completed_at=obj.completed_at,
            answers=await self.list_live_answers(obj.id),
            reopens=await self.list_reopens(obj.id),
        )

    def _to_model(
        self, entity: entities.AssessmentAttempt
    ) -> AssessmentAttemptModel:
        return AssessmentAttemptModel(
            id=entity.id,
            application_id=entity.application_id,
            template_type=entity.template_type,
            template_id=entity.template_id,
            status=entity.status,
        )

    async def list_for_application(
        self, application_id: uuid.UUID
    ) -> list[entities.AssessmentAttempt]:
        result = await self.db.execute(
            select(AssessmentAttemptModel).where(
                AssessmentAttemptModel.application_id == application_id
            )
        )
        return [await self._to_entity(obj) for obj in result.scalars().all()]

    async def start_attempt(self, attempt_id: uuid.UUID, started_at: datetime) -> None:
        obj = await self.db.get(AssessmentAttemptModel, attempt_id)
        if obj is None:
            return
        obj.status = "in_progress"
        obj.started_at = started_at

    async def complete_attempt(
        self, attempt_id: uuid.UUID, completed_at: datetime
    ) -> None:
        obj = await self.db.get(AssessmentAttemptModel, attempt_id)
        if obj is None:
            return
        obj.status = "completed"
        obj.completed_at = completed_at

    async def expire_attempt(self, attempt_id: uuid.UUID) -> None:
        obj = await self.db.get(AssessmentAttemptModel, attempt_id)
        if obj is None:
            return
        obj.status = "expired"

    async def reset_attempt(self, attempt_id: uuid.UUID) -> None:
        obj = await self.db.get(AssessmentAttemptModel, attempt_id)
        if obj is None:
            return
        obj.status = "not_started"
        obj.started_at = None
        obj.completed_at = None

    async def find_overdue_in_progress_attempts(
        self, now: datetime
    ) -> list[entities.AssessmentAttempt]:
        # No single FK target for template_id (3 possible tables), so this
        # can't be a plain join like the old single-table version — fetch
        # in-progress attempts, then look up each one's template by
        # dispatching on template_type.
        result = await self.db.execute(
            select(AssessmentAttemptModel).where(
                AssessmentAttemptModel.status == "in_progress",
                AssessmentAttemptModel.started_at.is_not(None),
            )
        )
        overdue = []
        for obj in result.scalars().all():
            template_model = _TEMPLATE_MODEL_BY_TYPE[TemplateType(obj.template_type)]
            template = await self.db.get(template_model, obj.template_id)
            if template is None or template.time_limit_minutes is None:
                continue
            deadline = obj.started_at + timedelta(minutes=template.time_limit_minutes)
            if deadline < now:
                overdue.append(await self._to_entity(obj))
        return overdue

    # --- answers -----------------------------------------------------

    def _answer_to_entity(
        self, obj: AssessmentAnswerModel
    ) -> entities.AssessmentAnswer:
        return entities.AssessmentAnswer(
            id=obj.id,
            attempt_id=obj.attempt_id,
            question_id=obj.question_id,
            question_started_at=obj.question_started_at,
            answered_at=obj.answered_at,
            answer_value=obj.answer_value,
            superseded_at=obj.superseded_at,
        )

    async def list_live_answers(
        self, attempt_id: uuid.UUID
    ) -> list[entities.AssessmentAnswer]:
        result = await self.db.execute(
            select(AssessmentAnswerModel).where(
                AssessmentAnswerModel.attempt_id == attempt_id,
                AssessmentAnswerModel.superseded_at.is_(None),
            )
        )
        return [self._answer_to_entity(row) for row in result.scalars().all()]

    async def get_live_answer_for_question(
        self, attempt_id: uuid.UUID, question_id: uuid.UUID
    ) -> entities.AssessmentAnswer | None:
        result = await self.db.execute(
            select(AssessmentAnswerModel).where(
                AssessmentAnswerModel.attempt_id == attempt_id,
                AssessmentAnswerModel.question_id == question_id,
                AssessmentAnswerModel.superseded_at.is_(None),
            )
        )
        obj = result.scalar_one_or_none()
        return self._answer_to_entity(obj) if obj is not None else None

    async def start_question(
        self,
        attempt_id: uuid.UUID,
        question_id: uuid.UUID,
        question_started_at: datetime,
    ) -> entities.AssessmentAnswer:
        answer_id = uuid.uuid4()
        self.db.add(
            AssessmentAnswerModel(
                id=answer_id,
                attempt_id=attempt_id,
                question_id=question_id,
                question_started_at=question_started_at,
            )
        )
        await self.db.flush()
        return await self.get_live_answer_for_question(attempt_id, question_id)

    async def submit_answer(
        self, answer_id: uuid.UUID, answer_value, answered_at: datetime
    ) -> None:
        obj = await self.db.get(AssessmentAnswerModel, answer_id)
        if obj is None:
            return
        obj.answer_value = answer_value
        obj.answered_at = answered_at

    async def supersede_answers(self, attempt_id: uuid.UUID, now: datetime) -> None:
        result = await self.db.execute(
            select(AssessmentAnswerModel).where(
                AssessmentAnswerModel.attempt_id == attempt_id,
                AssessmentAnswerModel.superseded_at.is_(None),
            )
        )
        for obj in result.scalars().all():
            obj.superseded_at = now

    # --- reopens -------------------------------------------------------

    async def list_reopens(
        self, attempt_id: uuid.UUID
    ) -> list[entities.AssessmentAttemptReopen]:
        result = await self.db.execute(
            select(AssessmentAttemptReopenModel)
            .where(AssessmentAttemptReopenModel.attempt_id == attempt_id)
            .order_by(AssessmentAttemptReopenModel.reopened_at.desc())
        )
        return [
            entities.AssessmentAttemptReopen(
                id=row.id,
                attempt_id=row.attempt_id,
                reopened_by_user_id=row.reopened_by_user_id,
                reason=row.reason,
                reopened_at=row.reopened_at,
            )
            for row in result.scalars().all()
        ]

    async def add_reopen(self, reopen: entities.AssessmentAttemptReopen) -> None:
        self.db.add(
            AssessmentAttemptReopenModel(
                id=reopen.id,
                attempt_id=reopen.attempt_id,
                reopened_by_user_id=reopen.reopened_by_user_id,
                reason=reopen.reason,
            )
        )
