import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.question_types import InvalidQuestionConfigError, QuestionType
from app.domains.assessments.culture_fit_templates import entities
from app.domains.assessments.culture_fit_templates.exceptions import (
    CultureFitQuestionNotFoundError,
    CultureFitQuestionsReorderError,
    CultureFitTemplateInUseError,
    CultureFitTemplateNotFoundError,
)
from app.domains.assessments.culture_fit_templates.service import (
    CultureFitTemplateService,
)


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
            question_type=QuestionType.SINGLE_CHOICE,
            config={"options": ["Alone", "Team", "Both"]},
            time_limit_seconds=30,
        )

        templates.add_question.assert_called_once()
        uow.commit.assert_called_once()


def make_question(**overrides) -> entities.CultureFitQuestion:
    defaults = dict(
        id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        order_index=0,
        prompt="Existing question",
        question_type=QuestionType.TEXT,
        config=None,
        time_limit_seconds=None,
    )
    defaults.update(overrides)
    return entities.CultureFitQuestion(**defaults)


class TestUpdateQuestion:
    async def test_rejects_unknown_question(self):
        service, templates, uow = make_service()
        templates.get_by_id.return_value = make_template(questions=[])

        with pytest.raises(CultureFitQuestionNotFoundError):
            await service.update_question(
                uuid.uuid4(),
                uuid.uuid4(),
                prompt="x",
                question_type=QuestionType.TEXT,
                config=None,
                time_limit_seconds=None,
            )
        templates.update_question.assert_not_called()

    async def test_happy_path_preserves_order_index_and_commits(self):
        service, templates, uow = make_service()
        q = make_question(order_index=2)
        templates.get_by_id.return_value = make_template(questions=[q])

        await service.update_question(
            q.template_id,
            q.id,
            prompt="Updated",
            question_type=QuestionType.TEXT,
            config=None,
            time_limit_seconds=None,
        )

        saved = templates.update_question.call_args.args[0]
        assert saved.order_index == 2
        uow.commit.assert_called_once()


class TestDeleteQuestion:
    async def test_rejects_unknown_question(self):
        service, templates, uow = make_service()
        templates.get_by_id.return_value = make_template(questions=[])

        with pytest.raises(CultureFitQuestionNotFoundError):
            await service.delete_question(uuid.uuid4(), uuid.uuid4())
        templates.delete_question.assert_not_called()

    async def test_happy_path_deletes_and_commits(self):
        service, templates, uow = make_service()
        q = make_question()
        templates.get_by_id.return_value = make_template(questions=[q])

        await service.delete_question(q.template_id, q.id)

        templates.delete_question.assert_called_once_with(q.id)
        uow.commit.assert_called_once()


class TestReorderQuestions:
    async def test_rejects_id_set_mismatch(self):
        service, templates, uow = make_service()
        q1, q2 = make_question(), make_question()
        templates.get_by_id.return_value = make_template(questions=[q1, q2])

        with pytest.raises(CultureFitQuestionsReorderError):
            await service.reorder_questions(q1.template_id, [q1.id])
        templates.reorder_questions.assert_not_called()

    async def test_happy_path_reorders_and_commits(self):
        service, templates, uow = make_service()
        q1, q2 = make_question(), make_question()
        templates.get_by_id.return_value = make_template(questions=[q1, q2])

        await service.reorder_questions(q1.template_id, [q2.id, q1.id])

        templates.reorder_questions.assert_called_once_with(
            q1.template_id, [q2.id, q1.id]
        )
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
