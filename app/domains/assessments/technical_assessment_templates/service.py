import uuid

from sqlalchemy.exc import IntegrityError

from app.core.question_types import validate_question_config
from app.core.unit_of_work import UnitOfWork
from app.domains.assessments.technical_assessment_templates import entities
from app.domains.assessments.technical_assessment_templates.exceptions import (
    TechnicalAssessmentQuestionNotFoundError,
    TechnicalAssessmentQuestionsReorderError,
    TechnicalAssessmentTemplateInUseError,
    TechnicalAssessmentTemplateNotFoundError,
)
from app.domains.assessments.technical_assessment_templates.repository import (
    TechnicalAssessmentTemplateRepository,
)


class TechnicalAssessmentTemplateService:
    def __init__(
        self, templates: TechnicalAssessmentTemplateRepository, uow: UnitOfWork
    ):
        self.templates = templates
        self.uow = uow

    async def create(
        self,
        *,
        title: str,
        description: str | None,
        instructions: str | None,
        time_limit_minutes: int | None,
    ) -> entities.TechnicalAssessmentTemplate:
        template_id = uuid.uuid4()
        await self.templates.add(
            entities.TechnicalAssessmentTemplate(
                id=template_id,
                title=title,
                description=description,
                instructions=instructions,
                time_limit_minutes=time_limit_minutes,
            )
        )
        await self.uow.commit()
        return await self.templates.get_by_id(template_id)

    async def get(self, template_id: uuid.UUID) -> entities.TechnicalAssessmentTemplate:
        template = await self.templates.get_by_id(template_id)
        if template is None:
            raise TechnicalAssessmentTemplateNotFoundError(
                f"Technical assessment template '{template_id}' not found"
            )
        return template

    async def update(
        self,
        template_id: uuid.UUID,
        *,
        title: str,
        description: str | None,
        instructions: str | None,
        time_limit_minutes: int | None,
    ) -> entities.TechnicalAssessmentTemplate:
        await self.get(template_id)
        await self.templates.update(
            entities.TechnicalAssessmentTemplate(
                id=template_id,
                title=title,
                description=description,
                instructions=instructions,
                time_limit_minutes=time_limit_minutes,
            )
        )
        await self.uow.commit()
        return await self.templates.get_by_id(template_id)

    async def delete(self, template_id: uuid.UUID) -> None:
        await self.get(template_id)
        await self.templates.delete(template_id)
        try:
            await self.uow.commit()
        except IntegrityError:
            await self.uow.rollback()
            raise TechnicalAssessmentTemplateInUseError(
                f"Technical assessment template '{template_id}' is still "
                "referenced by one or more job posts or assessment attempts"
            ) from None

    async def add_question(
        self,
        template_id: uuid.UUID,
        *,
        order_index: int,
        prompt: str,
        question_type: str,
        config: dict | None,
        time_limit_seconds: int | None,
    ) -> entities.TechnicalAssessmentTemplate:
        await self.get(template_id)
        validate_question_config(question_type, config)
        await self.templates.add_question(
            entities.TechnicalAssessmentQuestion(
                id=uuid.uuid4(),
                template_id=template_id,
                order_index=order_index,
                prompt=prompt,
                question_type=question_type,
                config=config,
                time_limit_seconds=time_limit_seconds,
            )
        )
        await self.uow.commit()
        return await self.templates.get_by_id(template_id)

    async def update_question(
        self,
        template_id: uuid.UUID,
        question_id: uuid.UUID,
        *,
        prompt: str,
        question_type: str,
        config: dict | None,
        time_limit_seconds: int | None,
    ) -> entities.TechnicalAssessmentTemplate:
        template = await self.get(template_id)
        existing = self._require_question(template, question_id)
        validate_question_config(question_type, config)
        await self.templates.update_question(
            entities.TechnicalAssessmentQuestion(
                id=question_id,
                template_id=template_id,
                order_index=existing.order_index,
                prompt=prompt,
                question_type=question_type,
                config=config,
                time_limit_seconds=time_limit_seconds,
            )
        )
        await self.uow.commit()
        return await self.templates.get_by_id(template_id)

    async def delete_question(
        self, template_id: uuid.UUID, question_id: uuid.UUID
    ) -> entities.TechnicalAssessmentTemplate:
        template = await self.get(template_id)
        self._require_question(template, question_id)
        await self.templates.delete_question(question_id)
        await self.uow.commit()
        return await self.templates.get_by_id(template_id)

    async def reorder_questions(
        self, template_id: uuid.UUID, question_ids: list[uuid.UUID]
    ) -> entities.TechnicalAssessmentTemplate:
        template = await self.get(template_id)
        current = {q.id for q in template.questions}
        if len(question_ids) != len(current) or set(question_ids) != current:
            raise TechnicalAssessmentQuestionsReorderError(
                "question_ids must list every current question of this template "
                "exactly once"
            )
        await self.templates.reorder_questions(template_id, question_ids)
        await self.uow.commit()
        return await self.templates.get_by_id(template_id)

    @staticmethod
    def _require_question(
        template: entities.TechnicalAssessmentTemplate, question_id: uuid.UUID
    ) -> entities.TechnicalAssessmentQuestion:
        for question in template.questions:
            if question.id == question_id:
                return question
        raise TechnicalAssessmentQuestionNotFoundError(
            f"Question '{question_id}' not found on this technical assessment template"
        )
