import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, AsyncMock

import pytest

from app.core.question_types import InvalidAnswerValueError, QuestionType
from app.domains.applications import entities as application_entities
from app.domains.applications.enums import ApplicationStatus
from app.domains.assessments import entities
from app.domains.assessments.enums import AttemptStatus, TemplateType
from app.domains.assessments.exceptions import (
    AssessmentAttemptExpiredError,
    AssessmentAttemptNotFoundError,
    InvalidAssessmentAttemptReopenError,
    NotCurrentQuestionError,
)
from app.domains.assessments.service import AssessmentService
from app.domains.auth import entities as auth_entities
from app.domains.technical_assessment_templates import (
    entities as technical_template_entities,
)


def make_service():
    attempts = AsyncMock()
    pre_assessment_templates = AsyncMock()
    culture_fit_templates = AsyncMock()
    technical_assessment_templates = AsyncMock()
    job_posts = AsyncMock()
    applications = AsyncMock()
    uow = AsyncMock()
    service = AssessmentService(
        attempts,
        pre_assessment_templates,
        culture_fit_templates,
        technical_assessment_templates,
        job_posts,
        applications,
        uow,
    )
    return (
        service,
        attempts,
        technical_assessment_templates,
        job_posts,
        applications,
        uow,
    )


def make_user(**overrides) -> auth_entities.User:
    defaults = dict(
        id=uuid.uuid4(),
        first_name="Ana",
        middle_initial=None,
        last_name="Applicant",
        contact_number="123",
        email="ana@example.com",
        password_hash="hashed",
        role_id=uuid.uuid4(),
        role="applicant",
        resume_object_key="applicant_resume/x/resume.pdf",
    )
    defaults.update(overrides)
    return auth_entities.User(**defaults)


def make_application(**overrides) -> application_entities.Application:
    defaults = dict(
        id=uuid.uuid4(),
        job_post_id=uuid.uuid4(),
        applicant_id=uuid.uuid4(),
        status=ApplicationStatus.APPLIED,
        resume_object_key="applicant_resume/x/resume.pdf",
    )
    defaults.update(overrides)
    return application_entities.Application(**defaults)


def make_question(
    **overrides,
) -> technical_template_entities.TechnicalAssessmentQuestion:
    defaults = dict(
        id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        order_index=1,
        prompt="How comfortable are you with Python?",
        question_type=QuestionType.RATING,
        config={"min": 1, "max": 5},
        time_limit_seconds=None,
    )
    defaults.update(overrides)
    return technical_template_entities.TechnicalAssessmentQuestion(**defaults)


def make_template(
    **overrides,
) -> technical_template_entities.TechnicalAssessmentTemplate:
    defaults = dict(
        id=uuid.uuid4(),
        title="Technical",
        description=None,
        instructions=None,
        time_limit_minutes=None,
        questions=[],
    )
    defaults.update(overrides)
    return technical_template_entities.TechnicalAssessmentTemplate(**defaults)


def make_attempt(**overrides) -> entities.AssessmentAttempt:
    defaults = dict(
        id=uuid.uuid4(),
        application_id=uuid.uuid4(),
        template_type=TemplateType.TECHNICAL,
        template_id=uuid.uuid4(),
        status=AttemptStatus.NOT_STARTED,
        started_at=None,
        completed_at=None,
    )
    defaults.update(overrides)
    return entities.AssessmentAttempt(**defaults)


def make_answer(**overrides) -> entities.AssessmentAnswer:
    defaults = dict(
        id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        question_id=uuid.uuid4(),
        question_started_at=datetime.now(UTC),
        answered_at=None,
        answer_value=None,
    )
    defaults.update(overrides)
    return entities.AssessmentAnswer(**defaults)


class TestCreateAttemptsForApplication:
    async def test_creates_one_attempt_per_attached_template(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        job_post = AsyncMock(
            pre_assessment_template_id=uuid.uuid4(),
            culture_fit_template_id=uuid.uuid4(),
            technical_assessment_template_id=uuid.uuid4(),
        )
        job_posts.get_by_id.return_value = job_post

        await service.create_attempts_for_application(uuid.uuid4(), uuid.uuid4())

        assert attempts.add.call_count == 3
        uow.commit.assert_called_once()

    async def test_only_creates_attempts_for_attached_types(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        job_post = AsyncMock(
            pre_assessment_template_id=None,
            culture_fit_template_id=None,
            technical_assessment_template_id=uuid.uuid4(),
        )
        job_posts.get_by_id.return_value = job_post

        await service.create_attempts_for_application(uuid.uuid4(), uuid.uuid4())

        assert attempts.add.call_count == 1

    async def test_noop_if_job_post_missing(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        job_posts.get_by_id.return_value = None

        await service.create_attempts_for_application(uuid.uuid4(), uuid.uuid4())

        attempts.add.assert_not_called()


class TestStartQuestion:
    async def test_non_owner_gets_not_found(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        attempt = make_attempt()
        attempts.get_by_id.return_value = attempt
        applications.get_by_id.return_value = make_application(
            applicant_id=uuid.uuid4()
        )

        with pytest.raises(AssessmentAttemptNotFoundError):
            await service.start_question(attempt.id, uuid.uuid4(), make_user())

    async def test_starts_first_question_and_attempt(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        user = make_user()
        q1 = make_question(order_index=1)
        q2 = make_question(order_index=2)
        attempt = make_attempt(status=AttemptStatus.NOT_STARTED)
        applications.get_by_id.return_value = make_application(
            applicant_id=user.id
        )
        attempts.get_by_id.return_value = attempt
        templates.get_by_id.return_value = make_template(questions=[q1, q2])
        attempts.list_live_answers.return_value = []

        await service.start_question(attempt.id, q1.id, user)

        attempts.start_attempt.assert_called_once()
        attempts.start_question.assert_called_once_with(attempt.id, q1.id, ANY)
        uow.commit.assert_called_once()

    async def test_rejects_out_of_order_question(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        user = make_user()
        q1 = make_question(order_index=1)
        q2 = make_question(order_index=2)
        attempt = make_attempt(status=AttemptStatus.NOT_STARTED)
        applications.get_by_id.return_value = make_application(applicant_id=user.id)
        attempts.get_by_id.return_value = attempt
        templates.get_by_id.return_value = make_template(questions=[q1, q2])
        attempts.list_live_answers.return_value = []

        with pytest.raises(NotCurrentQuestionError):
            await service.start_question(attempt.id, q2.id, user)

    async def test_expired_attempt_rejects_immediately(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        user = make_user()
        attempt = make_attempt(status=AttemptStatus.EXPIRED)
        applications.get_by_id.return_value = make_application(applicant_id=user.id)
        attempts.get_by_id.return_value = attempt
        templates.get_by_id.return_value = make_template()

        with pytest.raises(AssessmentAttemptExpiredError):
            await service.start_question(attempt.id, uuid.uuid4(), user)

    async def test_overall_timer_elapsed_expires_attempt(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        user = make_user()
        started_at = datetime.now(UTC) - timedelta(minutes=61)
        attempt = make_attempt(
            status=AttemptStatus.IN_PROGRESS, started_at=started_at
        )
        applications.get_by_id.return_value = make_application(applicant_id=user.id)
        attempts.get_by_id.return_value = attempt
        templates.get_by_id.return_value = make_template(time_limit_minutes=60)

        with pytest.raises(AssessmentAttemptExpiredError):
            await service.start_question(attempt.id, uuid.uuid4(), user)

        attempts.expire_attempt.assert_called_once_with(attempt.id)


class TestSubmitAnswer:
    async def test_completes_attempt_on_last_question(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        user = make_user()
        q1 = make_question(order_index=1, config={"min": 1, "max": 5})
        attempt = make_attempt(
            status=AttemptStatus.IN_PROGRESS, started_at=datetime.now(UTC)
        )
        applications.get_by_id.return_value = make_application(applicant_id=user.id)
        attempts.get_by_id.return_value = attempt
        templates.get_by_id.return_value = make_template(
            questions=[q1], time_limit_minutes=None
        )
        answer = make_answer(question_id=q1.id, answer_value=None)
        attempts.list_live_answers.return_value = [answer]

        await service.submit_answer(attempt.id, q1.id, 3, user)

        attempts.submit_answer.assert_called_once()
        attempts.complete_attempt.assert_called_once()
        uow.commit.assert_called_once()

    async def test_rejects_invalid_answer_value(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        user = make_user()
        q1 = make_question(order_index=1, config={"min": 1, "max": 5})
        attempt = make_attempt(status=AttemptStatus.IN_PROGRESS)
        applications.get_by_id.return_value = make_application(applicant_id=user.id)
        attempts.get_by_id.return_value = attempt
        templates.get_by_id.return_value = make_template(
            questions=[q1], time_limit_minutes=None
        )
        answer = make_answer(question_id=q1.id, answer_value=None)
        attempts.list_live_answers.return_value = [answer]

        with pytest.raises(InvalidAnswerValueError):
            await service.submit_answer(attempt.id, q1.id, 99, user)

        attempts.submit_answer.assert_not_called()

    async def test_rejects_answering_a_question_not_yet_started(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        user = make_user()
        q1 = make_question(order_index=1)
        attempt = make_attempt(status=AttemptStatus.IN_PROGRESS)
        applications.get_by_id.return_value = make_application(applicant_id=user.id)
        attempts.get_by_id.return_value = attempt
        templates.get_by_id.return_value = make_template(
            questions=[q1], time_limit_minutes=None
        )
        attempts.list_live_answers.return_value = []

        with pytest.raises(NotCurrentQuestionError):
            await service.submit_answer(attempt.id, q1.id, 3, user)


class TestReopen:
    async def test_rejects_non_expired_attempt(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        attempt = make_attempt(status=AttemptStatus.IN_PROGRESS)
        attempts.get_by_id.return_value = attempt

        with pytest.raises(InvalidAssessmentAttemptReopenError):
            await service.reopen(attempt.id, reason="please", current_user=make_user())

    async def test_rejects_when_application_disqualified(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        attempt = make_attempt(status=AttemptStatus.EXPIRED)
        attempts.get_by_id.return_value = attempt
        applications.get_by_id.return_value = make_application(
            status=ApplicationStatus.DISQUALIFIED
        )

        with pytest.raises(InvalidAssessmentAttemptReopenError):
            await service.reopen(attempt.id, reason="please", current_user=make_user())

    async def test_happy_path_supersedes_resets_and_logs(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        attempt = make_attempt(status=AttemptStatus.EXPIRED)
        attempts.get_by_id.return_value = attempt
        applications.get_by_id.return_value = make_application(
            status=ApplicationStatus.APPLIED
        )
        hr_user = make_user(role="hr")

        await service.reopen(attempt.id, reason="System outage", current_user=hr_user)

        attempts.supersede_answers.assert_called_once()
        attempts.reset_attempt.assert_called_once_with(attempt.id)
        attempts.add_reopen.assert_called_once()
        uow.commit.assert_called_once()


class TestSchedulerHelpers:
    async def test_expire_overdue_attempts_expires_each_found(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        overdue = [make_attempt(), make_attempt()]
        attempts.find_overdue_in_progress_attempts.return_value = overdue

        result = await service.expire_overdue_attempts()

        assert attempts.expire_attempt.call_count == 2
        assert set(result) == {a.id for a in overdue}
        uow.commit.assert_called_once()

    async def test_is_application_fully_assessed_true_when_no_attempts(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        attempts.list_for_application.return_value = []

        assert await service.is_application_fully_assessed(uuid.uuid4()) is True

    async def test_is_application_fully_assessed_false_when_incomplete(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        attempts.list_for_application.return_value = [
            make_attempt(status=AttemptStatus.COMPLETED),
            make_attempt(status=AttemptStatus.IN_PROGRESS),
        ]

        assert await service.is_application_fully_assessed(uuid.uuid4()) is False

    async def test_is_application_fully_assessed_true_when_all_completed(self):
        service, attempts, templates, job_posts, applications, uow = make_service()
        attempts.list_for_application.return_value = [
            make_attempt(status=AttemptStatus.COMPLETED),
            make_attempt(status=AttemptStatus.COMPLETED),
        ]

        assert await service.is_application_fully_assessed(uuid.uuid4()) is True
