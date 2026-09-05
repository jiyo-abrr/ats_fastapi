import uuid

from sqlalchemy import select

from app.core.repository import BaseRepository
from app.domains.culture_fit_templates import entities
from app.domains.culture_fit_templates.models import (
    CultureFitQuestion as CultureFitQuestionModel,
)
from app.domains.culture_fit_templates.models import (
    CultureFitTemplate as CultureFitTemplateModel,
)


class CultureFitTemplateRepository(
    BaseRepository[CultureFitTemplateModel, entities.CultureFitTemplate, uuid.UUID]
):
    model = CultureFitTemplateModel

    async def _to_entity(
        self, obj: CultureFitTemplateModel
    ) -> entities.CultureFitTemplate:
        return entities.CultureFitTemplate(
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
        self, entity: entities.CultureFitTemplate
    ) -> CultureFitTemplateModel:
        return CultureFitTemplateModel(
            id=entity.id,
            title=entity.title,
            description=entity.description,
            instructions=entity.instructions,
            time_limit_minutes=entity.time_limit_minutes,
        )

    async def _get_questions(
        self, template_id: uuid.UUID
    ) -> list[entities.CultureFitQuestion]:
        result = await self.db.execute(
            select(CultureFitQuestionModel)
            .where(CultureFitQuestionModel.template_id == template_id)
            .order_by(CultureFitQuestionModel.order_index)
        )
        return [self._question_to_entity(row) for row in result.scalars().all()]

    def _question_to_entity(
        self, obj: CultureFitQuestionModel
    ) -> entities.CultureFitQuestion:
        return entities.CultureFitQuestion(
            id=obj.id,
            template_id=obj.template_id,
            order_index=obj.order_index,
            prompt=obj.prompt,
            instructions=obj.instructions,
            question_type=obj.question_type,
            config=obj.config,
            time_limit_seconds=obj.time_limit_seconds,
        )

    async def update(self, entity: entities.CultureFitTemplate) -> None:
        obj = await self.db.get(CultureFitTemplateModel, entity.id)
        if obj is None:
            return
        obj.title = entity.title
        obj.description = entity.description
        obj.instructions = entity.instructions
        obj.time_limit_minutes = entity.time_limit_minutes

    async def add_question(self, question: entities.CultureFitQuestion) -> None:
        self.db.add(
            CultureFitQuestionModel(
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
    ) -> entities.CultureFitQuestion | None:
        obj = await self.db.get(CultureFitQuestionModel, question_id)
        return self._question_to_entity(obj) if obj is not None else None
