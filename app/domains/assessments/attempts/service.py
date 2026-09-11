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
    AssessmentDeadlinePassedError,
    InvalidAssessmentAttemptReopenError,
    MissingAssessmentTemplateError,
    NotCurrentQuestionError,
    ParentApplicationNotAcceptingAssessmentsError,
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

# Parent-application statuses in which an assessment attempt may still be
# started / answered. Everything else (withdrawn, denied, disqualified,
# success, failed) is terminal or already-decided — the applicant keeps
# read access to results but can't continue answering. See maintainability
# review F05.
_ASSESSMENT_ANSWERABLE_STATUSES = frozenset(
    {
        ApplicationStatus.APPLIED,
        ApplicationStatus.PRESCREENING,
        ApplicationStatus.INTERVIEW,
    }
)


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

    async def _get_template(self, attempt):
        """The attempt's template, preferring its frozen `template_snapshot`
        (taken at issuance — review F04/D03) over a live fetch, so an edit to
        the template after issuance can't change what an in-progress or
        completed attempt looked like. Only attempts created before the
        snapshot column existed fall back to the live template. `attempt` may
        be an entity or a raw ORM row (`summaries_for_applications` passes the
        latter) — both expose `template_type`/`template_id`/`template_snapshot`.
        May return None if there's no snapshot and the live template was
        deleted; callers that need it to exist use `_require_template`."""
        snapshot = attempt.template_snapshot
        if snapshot is not None:
            if isinstance(snapshot, entities.TemplateSnapshot):
                return snapshot
            return entities.TemplateSnapshot.from_json(snapshot)
        repo = self._template_repos[TemplateType(attempt.template_type)]
        return await repo.get_by_id(attempt.template_id)

    async def _require_template(self, attempt):
        template = await self._get_template(attempt)
        if template is None:
            raise MissingAssessmentTemplateError(
                f"The template for this attempt (type '{attempt.template_type}') "
                "no longer exists — it was removed after the attempt was created"
            )
        return template

    async def _with_total_questions(
        self, attempt: entities.AssessmentAttempt
    ) -> entities.AssessmentAttempt:
        """Populate `total_questions` from the attempt's template — called on
        every attempt returned to a router (list + submit + reopen), so the
        frontend gets progress without a gated template fetch."""
        template = await self._get_template(attempt)
        attempt.total_questions = len(template.questions) if template else 0
        return attempt

    async def create_attempts_for_application(
        self,
        application_id: uuid.UUID,
        job_post_id: uuid.UUID,
        commit: bool = True,
    ) -> None:
        """Stage one attempt per template the job post has attached.

        `commit=False` leaves the transaction open for the `apply_to_job` use
        case, which commits the application and its attempts together."""
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
            template = await self._template_repos[template_type].get_by_id(template_id)
            await self.attempts.add(
                entities.AssessmentAttempt(
                    id=uuid.uuid4(),
                    application_id=application_id,
                    template_type=template_type,
                    template_id=template_id,
                    status=AttemptStatus.NOT_STARTED,
                    template_snapshot=(
                        entities.TemplateSnapshot.from_template(template)
                        if template is not None
                        else None
                    ),
                )
            )
        if commit:
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

    @staticmethod
    def _parent_is_answerable(application) -> bool:
        try:
            return ApplicationStatus(application.status) in (
                _ASSESSMENT_ANSWERABLE_STATUSES
            )
        except ValueError:
            return False

    async def _require_answerable_parent(
        self, attempt: entities.AssessmentAttempt
    ) -> None:
        """Gate every assessment *mutation* on the parent application still
        being in a state that accepts assessment activity, and on the outer
        deadline not having passed. Read paths (get_attempt_detail, the HR
        review views) deliberately skip this."""
        application = await self.applications.get_by_id(attempt.application_id)
        if application is None:
            raise AssessmentAttemptNotFoundError(
                f"Assessment attempt '{attempt.id}' not found"
            )
        if not self._parent_is_answerable(application):
            raise ParentApplicationNotAcceptingAssessmentsError(
                f"This application is '{application.status}' — its assessments "
                "can no longer be answered"
            )
        if (
            application.assessment_deadline is not None
            and datetime.now(UTC) > application.assessment_deadline
        ):
            raise AssessmentDeadlinePassedError(
                "The assessment deadline for this application has passed"
            )

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
                if not await self.attempts.expire_attempt(attempt.id):
                    # Someone else already moved it out of in_progress in the
                    # meantime (e.g. the applicant's own submit_answer just
                    # completed it) — re-check against the real current state
                    # instead of wrongly claiming "expired" over a completion
                    # that actually landed first (review F02).
                    await self.uow.commit()
                    fresh = await self.attempts.get_by_id(attempt.id)
                    return await self._check_and_apply_layer2_expiry(fresh, template)
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
        await self._require_answerable_parent(attempt)
        template = await self._require_template(attempt)
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
        await self._require_answerable_parent(attempt)
        template = await self._require_template(attempt)
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
        # Reopening a terminal/decided application (withdrawn, denied, success,
        # failed) would produce an attempt the applicant can never continue —
        # start/submit are gated by _require_answerable_parent. Block it here so
        # the answers aren't superseded and the audit row isn't written for
        # nothing (review F05, second pass).
        if application is not None and not self._parent_is_answerable(application):
            raise InvalidAssessmentAttemptReopenError(
                f"Cannot reopen an attempt for an application that is "
                f"'{application.status}'"
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

    # Bounds one sweep call's work (review F16). in_progress attempts that get
    # expired/completed leave the scanned set, so a backlog bigger than this
    # drains over successive ticks rather than blowing up one tick's memory
    # and runtime.
    _SWEEP_BATCH_SIZE = 2000

    async def expire_overdue_attempts(self) -> list[uuid.UUID]:
        """Layer 2 sweep — called by the scheduled job, never a router.

        Expires attempts past their template's overall timer, and *completes*
        any still-in-progress attempt whose question sequence is fully
        consumed (every question answered, or its own per-question timer
        lapsed) — otherwise, with no overall timer, such an attempt would sit
        `in_progress` forever and the applicant would be disqualified for a
        test they actually finished (review F22).
        """
        now = datetime.now(UTC)
        overdue = await self.attempts.find_overdue_in_progress_attempts(
            now, limit=self._SWEEP_BATCH_SIZE
        )
        expired_ids = {attempt.id for attempt in overdue}
        for attempt in overdue:
            await self.attempts.expire_attempt(attempt.id)

        scanned = await self.attempts.list_in_progress_attempts(
            limit=self._SWEEP_BATCH_SIZE
        )
        for attempt in scanned:
            if attempt.id in expired_ids:
                continue
            template = await self._get_template(attempt)
            if template is None:
                continue
            answers = await self.attempts.list_live_answers(attempt.id)
            current, _ = self._compute_current_question(
                template.questions, {a.question_id: a for a in answers}, now
            )
            if current is None:
                await self.attempts.complete_attempt(attempt.id, now)

        await self.uow.commit()
        return list(expired_ids)

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

    async def summaries_for_applications(
        self, application_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[dict]]:
        """Per-application assessment roll-up for the job-post scorecard:
        status + answered/total per attached assessment, batched (≈4 queries
        for a whole page rather than N round trips)."""
        attempts = await self.attempts.list_models_for_applications(application_ids)
        answered = await self.attempts.answered_counts([a.id for a in attempts])
        total_cache: dict[tuple[str, str], int] = {}

        async def _total_questions(attempt) -> int:
            key = (attempt.template_type, str(attempt.template_id))
            if key not in total_cache:
                template = await self._get_template(attempt)
                total_cache[key] = len(template.questions) if template else 0
            return total_cache[key]

        out: dict[uuid.UUID, list[dict]] = {aid: [] for aid in application_ids}
        for a in attempts:
            out.setdefault(a.application_id, []).append(
                {
                    "template_type": a.template_type,
                    "status": a.status,
                    "answered_count": answered.get(a.id, 0),
                    "total_questions": await _total_questions(a),
                    "started_at": a.started_at,
                    "completed_at": a.completed_at,
                }
            )
        return out

    async def list_review_for_application(
        self, application_id: uuid.UUID
    ) -> list[dict]:
        """HR/admin comparison view: every attempt for an application, each
        with its full question list and the applicant's live answers. Unlike
        get_attempt_detail (applicant-facing, current question only) this
        exposes the whole attempt at once."""
        attempts = await self.attempts.list_for_application(application_id)
        reviews: list[dict] = []
        for attempt in attempts:
            template = await self._get_template(attempt)
            answers_by_question = {a.question_id: a for a in attempt.answers}
            questions = list(template.questions) if template else []
            questions.sort(key=lambda q: q.order_index)
            answered_count = sum(
                1 for a in attempt.answers if a.answer_value is not None
            )
            reviews.append(
                {
                    "attempt_id": attempt.id,
                    "template_type": attempt.template_type,
                    "template_title": template.title if template else "",
                    "status": attempt.status,
                    "started_at": attempt.started_at,
                    "completed_at": attempt.completed_at,
                    "total_questions": len(questions),
                    "answered_count": answered_count,
                    "reopen_count": len(attempt.reopens),
                    "questions": [
                        {
                            "question_id": q.id,
                            "order_index": q.order_index,
                            "prompt": q.prompt,
                            "question_type": q.question_type,
                            "answer_value": (
                                answers_by_question[q.id].answer_value
                                if q.id in answers_by_question
                                else None
                            ),
                            "answered_at": (
                                answers_by_question[q.id].answered_at
                                if q.id in answers_by_question
                                else None
                            ),
                        }
                        for q in questions
                    ],
                }
            )
        return reviews

    async def get_attempt_detail(
        self, attempt_id: uuid.UUID, current_user: auth_entities.User
    ) -> entities.AttemptDetail:
        """Read-only view for the attempt owner (applicant). Pure — never
        applies layer-2 expiry (that stays a side effect of start/submit);
        surfaces only the current question, matching the sequential rule."""
        attempt = await self._require_owned_attempt(attempt_id, current_user)
        template = await self._require_template(attempt)
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
