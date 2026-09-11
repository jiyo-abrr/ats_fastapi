"""F02 (rest) — assessment-attempt status writes (start/complete/expire) are
now conditional (`compare_and_set_status`), so a completion and an expiry
racing each other can't silently clobber one another. Not a data-integrity
fix (the live-answer partial unique index already prevented bad answer rows)
— this closes the status-field lost-update and gives a correct error instead
of a wrong one."""

from datetime import UTC, datetime, timedelta

from app.core.unit_of_work import UnitOfWork
from app.domains.applications.repository import ApplicationRepository
from app.domains.assessments.attempts.exceptions import (
    AssessmentAttemptAlreadyCompletedError,
)
from app.domains.assessments.attempts.repository import AssessmentAttemptRepository
from app.domains.assessments.attempts.service import AssessmentService
from app.domains.assessments.culture_fit_templates.repository import (
    CultureFitTemplateRepository,
)
from app.domains.assessments.pre_assessment_templates.repository import (
    PreAssessmentTemplateRepository,
)
from app.domains.assessments.technical_assessment_templates.repository import (
    TechnicalAssessmentTemplateRepository,
)
from app.domains.job_posts.repository import JobPostRepository
from tests.integration.factories import (
    make_application,
    make_attempt,
    make_job_post,
    make_pre_assessment_template,
    make_user,
)


def _service(db) -> AssessmentService:
    return AssessmentService(
        AssessmentAttemptRepository(db),
        PreAssessmentTemplateRepository(db),
        CultureFitTemplateRepository(db),
        TechnicalAssessmentTemplateRepository(db),
        JobPostRepository(db),
        ApplicationRepository(db),
        UnitOfWork(db),
    )


async def test_expire_does_not_clobber_a_completed_attempt(db_session):
    repo = AssessmentAttemptRepository(db_session)
    template = await make_pre_assessment_template(db_session, questions=1)
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session)
    application = await make_application(db_session, job_post=jp, applicant=applicant)
    attempt = await make_attempt(
        db_session,
        application=application,
        template_id=template.id,
        status="in_progress",
    )
    await db_session.flush()

    now = datetime.now(UTC)
    assert await repo.complete_attempt(attempt.id, now) is True

    # A racing expiry arrives after the completion already landed.
    assert await repo.expire_attempt(attempt.id) is False

    from sqlalchemy import select

    from app.domains.assessments.attempts.models import AssessmentAttempt

    status = (
        await db_session.execute(
            select(AssessmentAttempt.status).where(AssessmentAttempt.id == attempt.id)
        )
    ).scalar_one()
    assert status == "completed"


async def test_layer2_expiry_check_reports_completed_not_expired(db_session):
    """The realistic path: submit_answer completes the attempt; a concurrent
    request's layer-2 expiry check must then report "already completed", not
    wrongly claim "expired"."""
    template = await make_pre_assessment_template(db_session, questions=1)
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session)
    application = await make_application(db_session, job_post=jp, applicant=applicant)
    attempt = await make_attempt(
        db_session,
        application=application,
        template_id=template.id,
        status="in_progress",
        # started long enough ago that the (short, arbitrary) template timer
        # would normally read as overdue if re-checked naively.
    )
    await db_session.flush()

    repo = AssessmentAttemptRepository(db_session)
    now = datetime.now(UTC)
    # The DB row is completed...
    assert await repo.complete_attempt(attempt.id, now) is True
    await db_session.commit()

    # ...but this caller is still holding a stale, pre-completion view of the
    # attempt (still in_progress, started a while ago) — exactly what a
    # concurrent request that read before the completion committed would see.
    stale_view = await repo.get_by_id(attempt.id)
    stale_view.status = "in_progress"
    stale_view.started_at = now - timedelta(minutes=30)
    stale_view.completed_at = None

    svc = _service(db_session)

    class _OverdueTemplate:
        time_limit_minutes = 1  # short enough that the stale view reads overdue

    raised = None
    try:
        await svc._check_and_apply_layer2_expiry(  # noqa: SLF001
            stale_view, _OverdueTemplate()
        )
    except Exception as exc:  # noqa: BLE001
        raised = exc

    # Must report the real current state (completed), not wrongly claim expired.
    assert isinstance(raised, AssessmentAttemptAlreadyCompletedError)
