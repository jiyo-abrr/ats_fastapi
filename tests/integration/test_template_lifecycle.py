"""F04 — an assessment template with attempts pointing at it cannot be deleted
(there is no DB FK across that boundary, so the check lives in the
`delete_assessment_template` use case)."""

import pytest
from sqlalchemy import select

from app.core.unit_of_work import UnitOfWork
from app.domains.assessments.attempts.enums import TemplateType
from app.domains.assessments.attempts.models import AssessmentAttempt
from app.domains.assessments.attempts.repository import AssessmentAttemptRepository
from app.domains.assessments.pre_assessment_templates.exceptions import (
    PreAssessmentTemplateInUseError,
)
from app.domains.assessments.pre_assessment_templates.models import (
    PreAssessmentTemplate,
)
from app.domains.assessments.pre_assessment_templates.repository import (
    PreAssessmentTemplateRepository,
)
from app.domains.assessments.pre_assessment_templates.service import (
    PreAssessmentTemplateService,
)
from app.use_cases.delete_assessment_template import DeleteAssessmentTemplate
from tests.integration.factories import (
    make_application,
    make_attempt,
    make_job_post,
    make_pre_assessment_template,
    make_user,
)


def _use_case(db) -> DeleteAssessmentTemplate:
    return DeleteAssessmentTemplate(
        TemplateType.PRE_ASSESSMENT,
        PreAssessmentTemplateService(
            PreAssessmentTemplateRepository(db), UnitOfWork(db)
        ),
        AssessmentAttemptRepository(db),
    )


async def test_delete_blocked_when_an_attempt_references_the_template(db_session):
    template = await make_pre_assessment_template(db_session, questions=2)
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session)
    application = await make_application(db_session, job_post=jp, applicant=applicant)
    await make_attempt(db_session, application=application, template_id=template.id)
    await db_session.flush()

    with pytest.raises(PreAssessmentTemplateInUseError):
        await _use_case(db_session).execute(template.id)

    # still there
    still = (
        await db_session.execute(
            select(PreAssessmentTemplate.id).where(
                PreAssessmentTemplate.id == template.id
            )
        )
    ).scalar_one_or_none()
    assert still == template.id


async def test_delete_succeeds_with_no_attempts(db_session):
    template = await make_pre_assessment_template(db_session, questions=1)
    await db_session.flush()

    await _use_case(db_session).execute(template.id)
    await db_session.flush()

    gone = (
        await db_session.execute(
            select(PreAssessmentTemplate.id).where(
                PreAssessmentTemplate.id == template.id
            )
        )
    ).scalar_one_or_none()
    assert gone is None
    # its questions cascaded
    remaining_attempts = (await db_session.execute(select(AssessmentAttempt.id))).all()
    assert remaining_attempts == []
