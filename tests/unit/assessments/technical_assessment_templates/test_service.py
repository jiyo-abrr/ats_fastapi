import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.question_types import InvalidQuestionConfigError, QuestionType
from app.domains.assessments.technical_assessment_templates import entities
from app.domains.assessments.technical_assessment_templates.exceptions import (
    TechnicalAssessmentTemplateInUseError,
    TechnicalAssessmentTemplateNotFoundError,
)
from app.domains.assessments.technical_assessment_templates.service import (
    TechnicalAssessmentTemplateService,
)


def make_service():
    templates = AsyncMock()
    uow = AsyncMock()
    return TechnicalAssessmentTemplateService(templates, uow), templates, uow


def make_template(**overrides) -> entities.TechnicalAssessmentTemplate:
    defaults = dict(
        id=uuid.uuid4(),
        title="Technical Assessment",
        description=None,
        instructions=None,
        time_limit_minutes=60,
    )
    defaults.update(overrides)
    return entities.TechnicalAssessmentTemplate(**defaults)


class TestAddQuestion:
    async def test_rejects_missing_template(self):
        service, templates, uow = make_service()
        templates.get_by_id.return_value = None

        with pytest.raises(TechnicalAssessmentTemplateNotFoundError):
            await service.add_question(
                uuid.uuid4(),
                order_index=1,
                prompt="Explain async/await",
                instructions=None,
                question_type=QuestionType.LONG_TEXT,
                config=None,
                time_limit_seconds=None,
            )

    async def test_rejects_invalid_config_before_adding(self):
        service, templates, uow = make_service()
        templates.get_by_id.return_value = make_template()

        with pytest.raises(InvalidQuestionConfigError):
            await service.add_question(
                uuid.uuid4(),
                order_index=1,
                prompt="Pick one",
                instructions=None,
                question_type=QuestionType.MULTIPLE_CHOICE,
                config=None,
                time_limit_seconds=None,
            )

        templates.add_question.assert_not_called()

    async def test_happy_path_adds_and_commits(self):
        service, templates, uow = make_service()
        template = make_template()
        templates.get_by_id.return_value = template

        await service.add_question(
            template.id,
            order_index=1,
            prompt="Explain how async/await works in Python.",
            instructions=None,
            question_type=QuestionType.LONG_TEXT,
            config=None,
            time_limit_seconds=None,
        )

        templates.add_question.assert_called_once()
        uow.commit.assert_called_once()


class TestDelete:
    async def test_wraps_integrity_error_as_in_use(self):
        service, templates, uow = make_service()
        template = make_template()
        templates.get_by_id.return_value = template
        uow.commit.side_effect = IntegrityError("in use", None, None)

        with pytest.raises(TechnicalAssessmentTemplateInUseError):
            await service.delete(template.id)

        uow.rollback.assert_called_once()

    async def test_raises_not_found_for_missing_template(self):
        service, templates, uow = make_service()
        templates.get_by_id.return_value = None

        with pytest.raises(TechnicalAssessmentTemplateNotFoundError):
            await service.delete(uuid.uuid4())
