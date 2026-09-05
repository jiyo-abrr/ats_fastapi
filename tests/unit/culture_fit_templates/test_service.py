import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.question_types import InvalidQuestionConfigError, QuestionType
from app.domains.culture_fit_templates import entities
from app.domains.culture_fit_templates.exceptions import (
    CultureFitTemplateInUseError,
    CultureFitTemplateNotFoundError,
)
from app.domains.culture_fit_templates.service import CultureFitTemplateService


def make_service():
    templates = AsyncMock()
    uow = AsyncMock()
    return CultureFitTemplateService(templates, uow), templates, uow


def make_template(**overrides) -> entities.CultureFitTemplate:
    defaults = dict(
        id=uuid.uuid4(),
        title="Culture Fit",
        description=None,
        instructions=None,
        time_limit_minutes=30,
    )
    defaults.update(overrides)
    return entities.CultureFitTemplate(**defaults)


class TestAddQuestion:
    async def test_rejects_missing_template(self):
        service, templates, uow = make_service()
        templates.get_by_id.return_value = None

        with pytest.raises(CultureFitTemplateNotFoundError):
            await service.add_question(
                uuid.uuid4(),
                order_index=1,
                prompt="Rate this",
                instructions=None,
                question_type=QuestionType.RATING,
                config={"min": 1, "max": 5},
                time_limit_seconds=60,
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
                question_type=QuestionType.SINGLE_CHOICE,
                config=None,
                time_limit_seconds=30,
            )

        templates.add_question.assert_not_called()

    async def test_happy_path_adds_timed_question_and_commits(self):
        service, templates, uow = make_service()
        template = make_template()
        templates.get_by_id.return_value = template

        await service.add_question(
            template.id,
            order_index=1,
            prompt="Do you prefer working alone or in a team?",
            instructions=None,
            question_type=QuestionType.SINGLE_CHOICE,
            config={"options": ["Alone", "Team", "Both"]},
            time_limit_seconds=30,
        )

        templates.add_question.assert_called_once()
        uow.commit.assert_called_once()


class TestDelete:
    async def test_wraps_integrity_error_as_in_use(self):
        service, templates, uow = make_service()
        template = make_template()
        templates.get_by_id.return_value = template
        uow.commit.side_effect = IntegrityError("in use", None, None)

        with pytest.raises(CultureFitTemplateInUseError):
            await service.delete(template.id)

        uow.rollback.assert_called_once()

    async def test_raises_not_found_for_missing_template(self):
        service, templates, uow = make_service()
        templates.get_by_id.return_value = None

        with pytest.raises(CultureFitTemplateNotFoundError):
            await service.delete(uuid.uuid4())
