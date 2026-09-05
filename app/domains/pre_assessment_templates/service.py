import uuid

from sqlalchemy.exc import IntegrityError

from app.core.question_types import validate_question_config
from app.core.unit_of_work import UnitOfWork
from app.domains.pre_assessment_templates import entities
from app.domains.pre_assessment_templates.exceptions import (
    PreAssessmentTemplateInUseError,
    PreAssessmentTemplateNotFoundError,
)
from app.domains.pre_assessment_templates.repository import (
    PreAssessmentTemplateRepository,
)


class PreAssessmentTemplateService:
    def __init__(self, templates: PreAssessmentTemplateRepository, uow: UnitOfWork):
        self.templates = templates
        self.uow = uow

    async def create(
        self,
        *,
        title: str,
        description: str | None,
        instructions: str | None,
        time_limit_minutes: int | None,
    ) -> entities.PreAssessmentTemplate:
        template_id = uuid.uuid4()
        await self.templates.add(
            entities.PreAssessmentTemplate(
                id=template_id,
                title=title,
                description=description,
                instructions=instructions,
                time_limit_minutes=time_limit_minutes,
            )
        )
        await self.uow.commit()
        return await self.templates.get_by_id(template_id)

    async def get(self, template_id: uuid.UUID) -> entities.PreAssessmentTemplate:
        template = await self.templates.get_by_id(template_id)
        if template is None:
            raise PreAssessmentTemplateNotFoundError(
                f"Pre-assessment template '{template_id}' not found"
            )
        return template

    async def list(self) -> list[entities.PreAssessmentTemplate]:
        return await self.templates.list_all()

    async def update(
        self,
        template_id: uuid.UUID,
        *,
        title: str,
        description: str | None,
        instructions: str | None,
        time_limit_minutes: int | None,
    ) -> entities.PreAssessmentTemplate:
        await self.get(template_id)
        await self.templates.update(
            entities.PreAssessmentTemplate(
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
            raise PreAssessmentTemplateInUseError(
                f"Pre-assessment template '{template_id}' is still referenced "
                "by one or more job posts or assessment attempts"
            ) from None

    async def add_question(
        self,
        template_id: uuid.UUID,
        *,
        order_index: int,
        prompt: str,
        instructions: str | None,
        question_type: str,
        config: dict | None,
        time_limit_seconds: int | None,
    ) -> entities.PreAssessmentTemplate:
        await self.get(template_id)
        validate_question_config(question_type, config)
        await self.templates.add_question(
            entities.PreAssessmentQuestion(
                id=uuid.uuid4(),
                template_id=template_id,
                order_index=order_index,
                prompt=prompt,
                instructions=instructions,
                question_type=question_type,
                config=config,
                time_limit_seconds=time_limit_seconds,
            )
        )
        await self.uow.commit()
        return await self.templates.get_by_id(template_id)
