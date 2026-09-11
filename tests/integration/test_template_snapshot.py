"""F04 (rest) — an attempt's `template_snapshot` (taken at issuance) is what
the applicant sees and answers against, not the live template — so an HR edit
after issuance can't change historical meaning (D03)."""

from datetime import UTC, datetime, timedelta

from app.core.unit_of_work import UnitOfWork
from app.domains.applications.repository import ApplicationRepository
from app.domains.assessments.attempts.entities import TemplateSnapshot
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


async def test_editing_the_live_template_does_not_change_an_issued_attempt(
    db_session,
):
    template = await make_pre_assessment_template(db_session, questions=1)
    template_repo = PreAssessmentTemplateRepository(db_session)
    live_before = await template_repo.get_by_id(template.id)
    original_question = live_before.questions[0]
    original_prompt = original_question.prompt

    jp = await make_job_post(db_session)
    applicant = await make_user(db_session)
    application = await make_application(
        db_session,
        job_post=jp,
        applicant=applicant,
        assessment_deadline=datetime.now(UTC) + timedelta(days=4),
    )

    # Issue the attempt WITH a snapshot, the way create_attempts_for_application
    # does.
    live_template = live_before
    attempt = await make_attempt(
        db_session,
        application=application,
        template_id=template.id,
        status="not_started",
    )
    attempt.template_snapshot = TemplateSnapshot.from_template(live_template)
    # persist the snapshot onto the row we already inserted via the factory
    from app.domains.assessments.attempts.models import AssessmentAttempt

    row = await db_session.get(AssessmentAttempt, attempt.id)
    row.template_snapshot = attempt.template_snapshot.to_json()
    await db_session.flush()

    # HR edits the live template's question prompt AFTER issuance.
    original_question.prompt = "COMPLETELY DIFFERENT QUESTION"
    await template_repo.update_question(original_question)
    await db_session.flush()

    # The applicant's view must still show the original prompt.
    detail = await _service(db_session).get_attempt_detail(attempt.id, applicant)
    assert detail.current_question.prompt == original_prompt
    assert detail.current_question.prompt != "COMPLETELY DIFFERENT QUESTION"


async def test_missing_snapshot_falls_back_to_the_live_template(db_session):
    """Attempts created before this column existed have no snapshot — they
    keep working by falling back to a live fetch."""
    template = await make_pre_assessment_template(db_session, questions=1)
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session)
    application = await make_application(db_session, job_post=jp, applicant=applicant)
    attempt = await make_attempt(
        db_session, application=application, template_id=template.id
    )
    await db_session.flush()  # template_snapshot stays NULL

    live = await PreAssessmentTemplateRepository(db_session).get_by_id(template.id)
    detail = await _service(db_session).get_attempt_detail(attempt.id, applicant)
    assert detail.current_question.prompt == live.questions[0].prompt
