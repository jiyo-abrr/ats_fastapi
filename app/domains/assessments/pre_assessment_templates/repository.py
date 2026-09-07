import uuid

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.domains.assessments.pre_assessment_templates import entities
from app.domains.assessments.pre_assessment_templates.models import (
    PreAssessmentQuestion as PreAssessmentQuestionModel,
)
from app.domains.assessments.pre_assessment_templates.models import (
    PreAssessmentTemplate as PreAssessmentTemplateModel,
)


class PreAssessmentTemplateRepository(
    BaseRepository[
        PreAssessmentTemplateModel, entities.PreAssessmentTemplate, uuid.UUID
    ]
):
    model = PreAssessmentTemplateModel

    async def _to_entity(
        self, obj: PreAssessmentTemplateModel
    ) -> entities.PreAssessmentTemplate:
        return entities.PreAssessmentTemplate(
            id=obj.id,
            title=obj.title,
            description=obj.description,
            instructions=obj.instructions,
            time_limit_minutes=obj.time_limit_minutes,
            questions=await self._get_questions(obj.id),
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    def _to_model(
        self, entity: entities.PreAssessmentTemplate
    ) -> PreAssessmentTemplateModel:
        return PreAssessmentTemplateModel(
            id=entity.id,
            title=entity.title,
            description=entity.description,
            instructions=entity.instructions,
            time_limit_minutes=entity.time_limit_minutes,
        )

    async def _get_questions(
        self, template_id: uuid.UUID
    ) -> list[entities.PreAssessmentQuestion]:
        result = await self.db.execute(
            select(PreAssessmentQuestionModel)
            .where(PreAssessmentQuestionModel.template_id == template_id)
            .order_by(PreAssessmentQuestionModel.order_index)
        )
        return [self._question_to_entity(row) for row in result.scalars().all()]

    def _question_to_entity(
        self, obj: PreAssessmentQuestionModel
    ) -> entities.PreAssessmentQuestion:
        return entities.PreAssessmentQuestion(
            id=obj.id,
            template_id=obj.template_id,
            order_index=obj.order_index,
            prompt=obj.prompt,
            question_type=obj.question_type,
            config=obj.config,
            time_limit_seconds=obj.time_limit_seconds,
        )

    async def update(self, entity: entities.PreAssessmentTemplate) -> None:
        obj = await self.db.get(PreAssessmentTemplateModel, entity.id)
        if obj is None:
            return
        obj.title = entity.title
        obj.description = entity.description
        obj.instructions = entity.instructions
        obj.time_limit_minutes = entity.time_limit_minutes

    async def add_question(self, question: entities.PreAssessmentQuestion) -> None:
        self.db.add(
            PreAssessmentQuestionModel(
                id=question.id,
                template_id=question.template_id,
                order_index=question.order_index,
                prompt=question.prompt,
                question_type=question.question_type,
                config=question.config,
                time_limit_seconds=question.time_limit_seconds,
            )
        )

    async def get_question_by_id(
        self, question_id: uuid.UUID
    ) -> entities.PreAssessmentQuestion | None:
        obj = await self.db.get(PreAssessmentQuestionModel, question_id)
        return self._question_to_entity(obj) if obj is not None else None

    async def update_question(self, question: entities.PreAssessmentQuestion) -> None:
        obj = await self.db.get(PreAssessmentQuestionModel, question.id)
        if obj is None:
            return
        obj.prompt = question.prompt
        obj.question_type = question.question_type
        obj.config = question.config
        obj.time_limit_seconds = question.time_limit_seconds

    async def delete_question(self, question_id: uuid.UUID) -> None:
        obj = await self.db.get(PreAssessmentQuestionModel, question_id)
        if obj is not None:
            await self.db.delete(obj)

    async def reorder_questions(
        self, template_id: uuid.UUID, ordered_ids: list[uuid.UUID]
    ) -> None:
        result = await self.db.execute(
            select(PreAssessmentQuestionModel).where(
                PreAssessmentQuestionModel.template_id == template_id
            )
        )
        by_id = {q.id: q for q in result.scalars().all()}
        for position, question_id in enumerate(ordered_ids):
            obj = by_id.get(question_id)
            if obj is not None:
                obj.order_index = position
