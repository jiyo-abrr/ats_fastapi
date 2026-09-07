import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.question_types import validate_answer_value
from app.core.unit_of_work import UnitOfWork
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.repository import ApplicationRepository
from app.domains.assessments.attempts import entities
from app.domains.assessments.attempts.enums import AttemptStatus, TemplateType
from app.domains.assessments.attempts.exceptions import (
    AssessmentAttemptAlreadyCompletedError,
    AssessmentAttemptExpiredError,
    AssessmentAttemptNotFoundError,
    InvalidAssessmentAttemptReopenError,
    NotCurrentQuestionError,
)
from app.domains.assessments.attempts.repository import AssessmentAttemptRepository
from app.domains.assessments.culture_fit_templates.repository import (
    CultureFitTemplateRepository,
)
from app.domains.assessments.pre_assessment_templates.repository import (
    PreAssessmentTemplateRepository,
)
from app.domains.assessments.technical_assessment_templates.repository import (
    TechnicalAssessmentTemplateRepository,
)
from app.domains.auth import entities as auth_entities
from app.domains.job_posts.repository import JobPostRepository


class AssessmentService:
    def __init__(
        self,
        attempts: AssessmentAttemptRepository,
        pre_assessment_templates: PreAssessmentTemplateRepository,
        culture_fit_templates: CultureFitTemplateRepository,
        technical_assessment_templates: TechnicalAssessmentTemplateRepository,
        job_posts: JobPostRepository,
        applications: ApplicationRepository,
        uow: UnitOfWork,
    ):
        self.attempts = attempts
        self._template_repos = {
            TemplateType.PRE_ASSESSMENT: pre_assessment_templates,
            TemplateType.CULTURE_FIT: culture_fit_templates,
            TemplateType.TECHNICAL: technical_assessment_templates,
        }
        self.job_posts = job_posts
        self.applications = applications
        self.uow = uow

    async def _get_template(self, template_type: str, template_id: uuid.UUID):
        """Dispatches to whichever of the 3 template repositories owns this
        attempt's template — template_id alone is ambiguous without knowing
        which of the 3 independent domains it belongs to."""
        repo = self._template_repos[TemplateType(template_type)]
        return await repo.get_by_id(template_id)

    async def _with_total_questions(
        self, attempt: entities.AssessmentAttempt
    ) -> entities.AssessmentAttempt:
        """Populate `total_questions` from the attempt's template — called on
        every attempt returned to a router (list + submit + reopen), so the
        frontend gets progress without a gated template fetch."""
        template = await self._get_template(attempt.template_type, attempt.template_id)
        attempt.total_questions = len(template.questions) if template else 0
        return attempt

    async def create_attempts_for_application(
        self, application_id: uuid.UUID, job_post_id: uuid.UUID
    ) -> None:
        job_post = await self.job_posts.get_by_id(job_post_id)
        if job_post is None:
            return
        attached = {
            TemplateType.PRE_ASSESSMENT: job_post.pre_assessment_template_id,
            TemplateType.CULTURE_FIT: job_post.culture_fit_template_id,
            TemplateType.TECHNICAL: job_post.technical_assessment_template_id,
        }
        for template_type, template_id in attached.items():
            if template_id is None:
                continue
            await self.attempts.add(
                entities.AssessmentAttempt(
                    id=uuid.uuid4(),
                    application_id=application_id,
                    template_type=template_type,
                    template_id=template_id,
                    status=AttemptStatus.NOT_STARTED,
                )
            )
        await self.uow.commit()

    async def _require_owned_attempt(
        self, attempt_id: uuid.UUID, current_user: auth_entities.User
    ) -> entities.AssessmentAttempt:
        attempt = await self.attempts.get_by_id(attempt_id)
        if attempt is None:
            raise AssessmentAttemptNotFoundError(
                f"Assessment attempt '{attempt_id}' not found"
            )
        application = await self.applications.get_by_id(attempt.application_id)
        if application is None or application.applicant_id != current_user.id:
            raise AssessmentAttemptNotFoundError(
                f"Assessment attempt '{attempt_id}' not found"
            )
        return attempt

    async def _check_and_apply_layer2_expiry(
        self, attempt: entities.AssessmentAttempt, template
    ) -> entities.AssessmentAttempt:
        if attempt.status == AttemptStatus.EXPIRED:
            raise AssessmentAttemptExpiredError(
                f"Assessment attempt '{attempt.id}' has expired"
            )
        if attempt.status == AttemptStatus.COMPLETED:
            raise AssessmentAttemptAlreadyCompletedError(
                f"Assessment attempt '{attempt.id}' is already completed"
            )
        if (
            attempt.status == AttemptStatus.IN_PROGRESS
            and template.time_limit_minutes is not None
        ):
            deadline = attempt.started_at + timedelta(
                minutes=template.time_limit_minutes
            )
            if datetime.now(UTC) > deadline:
                await self.attempts.expire_attempt(attempt.id)
                await self.uow.commit()
                raise AssessmentAttemptExpiredError(
                    f"Assessment attempt '{attempt.id}' has expired"
                )
        return attempt

    def _compute_current_question(self, questions, answers_by_question, now):
        for question in questions:
            answer = answers_by_question.get(question.id)
            if answer is None:
                return question, None
            if answer.answer_value is not None:
                continue
            if question.time_limit_seconds is None:
                return question, answer
            deadline = answer.question_started_at + timedelta(
                seconds=question.time_limit_seconds
            )
            if now <= deadline:
                return question, answer
            # else: past its own timer, permanently closed — silently move on
        return None, None

    async def start_question(
        self,
        attempt_id: uuid.UUID,
        question_id: uuid.UUID,
        current_user: auth_entities.User,
    ) -> entities.AssessmentAnswer:
        attempt = await self._require_owned_attempt(attempt_id, current_user)
        template = await self._get_template(attempt.template_type, attempt.template_id)
        now = datetime.now(UTC)

        if attempt.status == AttemptStatus.NOT_STARTED:
            await self.attempts.start_attempt(attempt_id, now)
        else:
            attempt = await self._check_and_apply_layer2_expiry(attempt, template)

        answers = await self.attempts.list_live_answers(attempt_id)
        answers_by_question = {a.question_id: a for a in answers}
        current_question, current_answer = self._compute_current_question(
            template.questions, answers_by_question, now
        )

        if current_question is None:
            await self.attempts.complete_attempt(attempt_id, now)
            await self.uow.commit()
            raise AssessmentAttemptAlreadyCompletedError(
                f"Assessment attempt '{attempt_id}' is already completed"
            )

        if current_question.id != question_id:
            raise NotCurrentQuestionError(
                f"Question '{question_id}' is not the current question for this attempt"
            )

        if current_answer is not None:
            await self.uow.commit()
            return current_answer  # idempotent restart — timer not reset

        answer = await self.attempts.start_question(attempt_id, question_id, now)
        await self.uow.commit()
        return answer

    async def submit_answer(
        self,
        attempt_id: uuid.UUID,
        question_id: uuid.UUID,
        answer_value: Any,
        current_user: auth_entities.User,
    ) -> entities.AssessmentAttempt:
        attempt = await self._require_owned_attempt(attempt_id, current_user)
        template = await self._get_template(attempt.template_type, attempt.template_id)
        now = datetime.now(UTC)
        attempt = await self._check_and_apply_layer2_expiry(attempt, template)

        answers = await self.attempts.list_live_answers(attempt_id)
        answers_by_question = {a.question_id: a for a in answers}
        current_question, current_answer = self._compute_current_question(
            template.questions, answers_by_question, now
        )

        if (
            current_question is None
            or current_question.id != question_id
            or current_answer is None
        ):
            raise NotCurrentQuestionError(
                f"Question '{question_id}' is not currently awaiting an "
                "answer for this attempt"
            )

        validate_answer_value(
            current_question.question_type, current_question.config, answer_value
        )
        await self.attempts.submit_answer(current_answer.id, answer_value, now)

        answers_by_question[question_id] = entities.AssessmentAnswer(
            id=current_answer.id,
            attempt_id=attempt_id,
            question_id=question_id,
            question_started_at=current_answer.question_started_at,
            answered_at=now,
            answer_value=answer_value,
        )
        next_question, _ = self._compute_current_question(
            template.questions, answers_by_question, now
        )
        if next_question is None:
            await self.attempts.complete_attempt(attempt_id, now)

        await self.uow.commit()
        return await self._with_total_questions(
            await self.attempts.get_by_id(attempt_id)
        )

    async def reopen(
        self, attempt_id: uuid.UUID, *, reason: str, current_user: auth_entities.User
    ) -> entities.AssessmentAttempt:
        attempt = await self.attempts.get_by_id(attempt_id)
        if attempt is None:
            raise AssessmentAttemptNotFoundError(
                f"Assessment attempt '{attempt_id}' not found"
            )
        if attempt.status != AttemptStatus.EXPIRED:
            raise InvalidAssessmentAttemptReopenError(
                f"Cannot reopen an attempt with status '{attempt.status}' — "
                "only expired attempts can be reopened"
            )
        application = await self.applications.get_by_id(attempt.application_id)
        if (
            application is not None
            and application.status == ApplicationStatus.DISQUALIFIED
        ):
            raise InvalidAssessmentAttemptReopenError(
                "Cannot reopen an attempt for an already-disqualified "
                "application — extend the assessment deadline first"
            )

        now = datetime.now(UTC)
        await self.attempts.supersede_answers(attempt_id, now)
        await self.attempts.reset_attempt(attempt_id)
        await self.attempts.add_reopen(
            entities.AssessmentAttemptReopen(
                id=uuid.uuid4(),
                attempt_id=attempt_id,
                reopened_by_user_id=current_user.id,
                reason=reason,
            )
        )
        await self.uow.commit()
        return await self._with_total_questions(
            await self.attempts.get_by_id(attempt_id)
        )

    async def expire_overdue_attempts(self) -> list[uuid.UUID]:
        """Layer 2 sweep — called by the scheduled job, never a router."""
        now = datetime.now(UTC)
        overdue = await self.attempts.find_overdue_in_progress_attempts(now)
        for attempt in overdue:
            await self.attempts.expire_attempt(attempt.id)
        await self.uow.commit()
        return [attempt.id for attempt in overdue]

    async def is_application_fully_assessed(self, application_id: uuid.UUID) -> bool:
        """Called by the disqualification sweep — no attempts at all (a job
        post with nothing attached) counts as vacuously fully assessed."""
        attempts = await self.attempts.list_for_application(application_id)
        if not attempts:
            return True
        return all(attempt.status == AttemptStatus.COMPLETED for attempt in attempts)

    async def list_for_application(
        self, application_id: uuid.UUID
    ) -> list[entities.AssessmentAttempt]:
        attempts = await self.attempts.list_for_application(application_id)
        for attempt in attempts:
            await self._with_total_questions(attempt)
        return attempts

    async def get_attempt_detail(
        self, attempt_id: uuid.UUID, current_user: auth_entities.User
    ) -> entities.AttemptDetail:
        """Read-only view for the attempt owner (applicant). Pure — never
        applies layer-2 expiry (that stays a side effect of start/submit);
        surfaces only the current question, matching the sequential rule."""
        attempt = await self._require_owned_attempt(attempt_id, current_user)
        template = await self._get_template(attempt.template_type, attempt.template_id)
        now = datetime.now(UTC)
        answers = await self.attempts.list_live_answers(attempt_id)
        answers_by_question = {a.question_id: a for a in answers}
        answered_count = sum(1 for a in answers if a.answer_value is not None)
        current_question, current_answer = self._compute_current_question(
            template.questions, answers_by_question, now
        )
        return entities.AttemptDetail(
            attempt=attempt,
            template_title=template.title,
            template_instructions=template.instructions,
            time_limit_minutes=template.time_limit_minutes,
            total_questions=len(template.questions),
            answered_count=answered_count,
            current_question=current_question,
            current_answer=current_answer,
        )
