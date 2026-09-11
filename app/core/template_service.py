"""Shared CRUD/question-authoring logic for the 3 independent assessment
template domains (pre_assessment_templates, culture_fit_templates,
technical_assessment_templates — see CLAUDE.md's "Assessments" section).

Those 3 domains are deliberately kept independent — no shared base model, no
shared router, no shared repository contract beyond convention — but their
*services* turned out to be byte-for-byte identical business logic modulo
naming (review F20). `BaseTemplateService` is that shared logic, parametrized
by each domain's entity/exception classes via class attributes; each domain's
own `service.py` is a ~15-line subclass that just binds those attributes and
keeps its own name (`PreAssessmentTemplateService`, etc.) for imports and DI.

This is *not* a generic "configurable CRUD framework" — there is no
configuration surface beyond "which 4 types/label", and it only exists because
the 3 domains' logic was already, verifiably, the same logic. If a domain's
question-authoring rules ever need to diverge, override the specific method
on that domain's subclass rather than adding a flag here.

A repository passed in must expose the same method surface as
`PreAssessmentTemplateRepository` (get_by_id/add/update/delete/add_question/
update_question/delete_question/reorder_questions) — duck-typed, not a formal
Protocol, since the 3 repositories already match structurally and adding one
would just be ceremony.
"""

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy.exc import IntegrityError

from app.core.question_types import validate_question_config
from app.core.unit_of_work import UnitOfWork

TemplateT = TypeVar("TemplateT")
QuestionT = TypeVar("QuestionT")


class BaseTemplateService(Generic[TemplateT, QuestionT]):
    # Bound by each domain's subclass.
    template_entity_cls: type[TemplateT]
    question_entity_cls: type[QuestionT]
    not_found_error: type[Exception]
    in_use_error: type[Exception]
    question_not_found_error: type[Exception]
    reorder_error: type[Exception]
    # Lowercase, mid-sentence form — "pre-assessment", "culture-fit",
    # "technical assessment". Capitalized automatically at sentence start.
    label: str

    def __init__(self, templates: Any, uow: UnitOfWork):
        self.templates = templates
        self.uow = uow

    def _label_cap(self) -> str:
        return self.label[0].upper() + self.label[1:]

    async def create(
        self,
        *,
        title: str,
        description: str | None,
        instructions: str | None,
        time_limit_minutes: int | None,
    ) -> TemplateT:
        template_id = uuid.uuid4()
        await self.templates.add(
            self.template_entity_cls(
                id=template_id,
                title=title,
                description=description,
                instructions=instructions,
                time_limit_minutes=time_limit_minutes,
            )
        )
        await self.uow.commit()
        return await self.templates.get_by_id(template_id)

    async def get(self, template_id: uuid.UUID) -> TemplateT:
        template = await self.templates.get_by_id(template_id)
        if template is None:
            raise self.not_found_error(
                f"{self._label_cap()} template '{template_id}' not found"
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
    ) -> TemplateT:
        await self.get(template_id)
        await self.templates.update(
            self.template_entity_cls(
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
            raise self.in_use_error(
                f"{self._label_cap()} template '{template_id}' is still "
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
    ) -> TemplateT:
        await self.get(template_id)
        validate_question_config(question_type, config)
        await self.templates.add_question(
            self.question_entity_cls(
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
    ) -> TemplateT:
        template = await self.get(template_id)
        existing = self._require_question(template, question_id)
        validate_question_config(question_type, config)
        await self.templates.update_question(
            self.question_entity_cls(
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
    ) -> TemplateT:
        template = await self.get(template_id)
        self._require_question(template, question_id)
        await self.templates.delete_question(question_id)
        await self.uow.commit()
        return await self.templates.get_by_id(template_id)

    async def reorder_questions(
        self, template_id: uuid.UUID, question_ids: list[uuid.UUID]
    ) -> TemplateT:
        template = await self.get(template_id)
        current = {q.id for q in template.questions}
        if len(question_ids) != len(current) or set(question_ids) != current:
            raise self.reorder_error(
                "question_ids must list every current question of this "
                "template exactly once"
            )
        await self.templates.reorder_questions(template_id, question_ids)
        await self.uow.commit()
        return await self.templates.get_by_id(template_id)

    def _require_question(
        self, template: TemplateT, question_id: uuid.UUID
    ) -> QuestionT:
        for question in template.questions:
            if question.id == question_id:
                return question
        raise self.question_not_found_error(
            f"Question '{question_id}' not found on this {self.label} template"
        )
