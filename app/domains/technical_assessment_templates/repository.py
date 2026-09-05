import uuid

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.domains.technical_assessment_templates import entities
from app.domains.technical_assessment_templates.models import (
    TechnicalAssessmentQuestion as TechnicalAssessmentQuestionModel,
)
from app.domains.technical_assessment_templates.models import (
    TechnicalAssessmentTemplate as TechnicalAssessmentTemplateModel,
)


class TechnicalAssessmentTemplateRepository(
    BaseRepository[
        TechnicalAssessmentTemplateModel,
        entities.TechnicalAssessmentTemplate,
        uuid.UUID,
    ]
):
    model = TechnicalAssessmentTemplateModel

    async def _to_entity(
        self, obj: TechnicalAssessmentTemplateModel
    ) -> entities.TechnicalAssessmentTemplate:
        return entities.TechnicalAssessmentTemplate(
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
        self, entity: entities.TechnicalAssessmentTemplate
    ) -> TechnicalAssessmentTemplateModel:
        return TechnicalAssessmentTemplateModel(
            id=entity.id,
            title=entity.title,
            description=entity.description,
            instructions=entity.instructions,
            time_limit_minutes=entity.time_limit_minutes,
        )

    async def _get_questions(
        self, template_id: uuid.UUID
    ) -> list[entities.TechnicalAssessmentQuestion]:
        result = await self.db.execute(
            select(TechnicalAssessmentQuestionModel)
            .where(TechnicalAssessmentQuestionModel.template_id == template_id)
            .order_by(TechnicalAssessmentQuestionModel.order_index)
        )
        return [self._question_to_entity(row) for row in result.scalars().all()]

    def _question_to_entity(
        self, obj: TechnicalAssessmentQuestionModel
    ) -> entities.TechnicalAssessmentQuestion:
        return entities.TechnicalAssessmentQuestion(
            id=obj.id,
            template_id=obj.template_id,
            order_index=obj.order_index,
            prompt=obj.prompt,
            instructions=obj.instructions,
            question_type=obj.question_type,
            config=obj.config,
            time_limit_seconds=obj.time_limit_seconds,
        )

    async def update(self, entity: entities.TechnicalAssessmentTemplate) -> None:
        obj = await self.db.get(TechnicalAssessmentTemplateModel, entity.id)
        if obj is None:
            return
        obj.title = entity.title
        obj.description = entity.description
        obj.instructions = entity.instructions
        obj.time_limit_minutes = entity.time_limit_minutes

    async def add_question(
        self, question: entities.TechnicalAssessmentQuestion
    ) -> None:
        self.db.add(
            TechnicalAssessmentQuestionModel(
                id=question.id,
                template_id=question.template_id,
                order_index=question.order_index,
                prompt=question.prompt,
                instructions=question.instructions,
                question_type=question.question_type,
                config=question.config,
                time_limit_seconds=question.time_limit_seconds,
            )
        )

    async def get_question_by_id(
        self, question_id: uuid.UUID
    ) -> entities.TechnicalAssessmentQuestion | None:
        obj = await self.db.get(TechnicalAssessmentQuestionModel, question_id)
        return self._question_to_entity(obj) if obj is not None else None
