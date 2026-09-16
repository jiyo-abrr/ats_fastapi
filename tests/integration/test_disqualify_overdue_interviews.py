"""Interview-stage disqualification sweep — the query that finds
`interview`-stage applications whose interview_booking_deadline has passed
with no slot ever confirmed (app/scripts/disqualify_overdue_interviews.py).
"""

from datetime import UTC, datetime, timedelta

from app.core.unit_of_work import UnitOfWork
from app.domains.applications.repository import ApplicationRepository
from app.domains.applications.service import ApplicationService
from app.domains.interviews.availability_repository import (
    InterviewAvailabilityRepository,
)
from app.domains.interviews.availability_service import InterviewAvailabilityService
from app.domains.interviews.repository import InterviewRepository
from app.domains.interviews.scheduling_service import InterviewService
from app.domains.interviews.schemas import (
    InterviewRequestIn,
    InterviewSlotIn,
    SelectSlotIn,
)
from app.domains.job_posts.repository import JobPostRepository
from app.domains.rbac.repository import RolePermissionRepository
from tests.integration.factories import make_application, make_job_post, make_user

_PAST = datetime.now(UTC) - timedelta(days=1)
_FUTURE = datetime.now(UTC) + timedelta(days=5)


def _services(db_session):
    uow = UnitOfWork(db_session)
    availability = InterviewAvailabilityService(
        InterviewAvailabilityRepository(db_session), uow
    )
    interview_service = InterviewService(
        InterviewRepository(db_session), availability, uow
    )
    application_service = ApplicationService(
        ApplicationRepository(db_session),
        JobPostRepository(db_session),
        RolePermissionRepository(db_session),
        uow,
    )
    return interview_service, application_service


async def test_finds_overdue_application_with_no_slot_picked(db_session):
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session, role="applicant")
    app = await make_application(
        db_session,
        job_post=jp,
        applicant=applicant,
        status="interview",
        interview_booking_deadline=_PAST,
    )
    await db_session.commit()

    ids = await InterviewRepository(db_session).list_overdue_interview_ids(
        datetime.now(UTC)
    )

    assert app.id in ids


async def test_excludes_application_that_already_booked_a_slot(db_session):
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session, role="applicant")
    hr = await make_user(db_session, role="hr")
    app = await make_application(
        db_session,
        job_post=jp,
        applicant=applicant,
        status="interview",
        interview_booking_deadline=_PAST,
    )
    await db_session.commit()

    interviews, _ = _services(db_session)
    request = await interviews.set_request(
        app.id,
        InterviewRequestIn(mode="video", slots=[InterviewSlotIn(starts_at=_FUTURE)]),
        created_by_user_id=hr.id,
    )
    await interviews.select_slot(
        app.id,
        SelectSlotIn(slot_id=request.slots[0].id),
        selected_by_user_id=applicant.id,
    )

    ids = await InterviewRepository(db_session).list_overdue_interview_ids(
        datetime.now(UTC)
    )

    assert app.id not in ids


async def test_excludes_application_whose_deadline_has_not_passed_yet(db_session):
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session, role="applicant")
    app = await make_application(
        db_session,
        job_post=jp,
        applicant=applicant,
        status="interview",
        interview_booking_deadline=_FUTURE,
    )
    await db_session.commit()

    ids = await InterviewRepository(db_session).list_overdue_interview_ids(
        datetime.now(UTC)
    )

    assert app.id not in ids


async def test_disqualify_interview_overdue_flips_status(db_session):
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session, role="applicant")
    app = await make_application(
        db_session,
        job_post=jp,
        applicant=applicant,
        status="interview",
        interview_booking_deadline=_PAST,
    )
    await db_session.commit()

    _, applications = _services(db_session)
    await applications.disqualify_interview_overdue(app.id)

    await db_session.refresh(app)
    assert app.status == "disqualified"
