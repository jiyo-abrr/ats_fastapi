"""F03 (full) — the database itself rejects two confirmed interview slots
whose time ranges overlap, via the `ex_interview_slots_no_overlap` EXCLUDE
constraint. This is the race the Python-side `_overlaps_confirmed` check alone
can't fully close (two concurrent requests can both pass it before either
commits)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.interviews.models import InterviewRequest, InterviewSlot
from tests.integration.factories import make_application, make_job_post, make_user


async def _make_request(db, *, application_id) -> InterviewRequest:
    creator = await make_user(db, role="hr", email=f"{uuid.uuid4().hex[:10]}@x.com")
    req = InterviewRequest(
        id=uuid.uuid4(),
        application_id=application_id,
        created_by_user_id=creator.id,
        mode="video",
        duration_minutes=45,
        self_scheduled=False,
    )
    db.add(req)
    await db.flush()
    return req


async def _confirmed_slot(db, *, request: InterviewRequest, starts_at: datetime):
    slot = InterviewSlot(
        id=uuid.uuid4(),
        request_id=request.id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=request.duration_minutes),
        selected_at=datetime.now(UTC),
    )
    db.add(slot)
    return slot


async def _new_application(db):
    jp = await make_job_post(db, status="published")
    applicant = await make_user(
        db, role="applicant", email=f"{uuid.uuid4().hex[:10]}@x.com"
    )
    return await make_application(db, job_post=jp, applicant=applicant)


async def test_overlapping_confirmed_slots_are_rejected_by_the_database(db_session):
    start = datetime(2026, 12, 1, 9, tzinfo=UTC)

    app_a = await _new_application(db_session)
    req_a = await _make_request(db_session, application_id=app_a.id)
    await _confirmed_slot(db_session, request=req_a, starts_at=start)
    await db_session.flush()

    app_b = await _new_application(db_session)
    req_b = await _make_request(db_session, application_id=app_b.id)
    # overlaps [09:00, 09:45) by 15 minutes
    await _confirmed_slot(
        db_session, request=req_b, starts_at=start + timedelta(minutes=30)
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_back_to_back_confirmed_slots_are_allowed(db_session):
    start = datetime(2026, 12, 1, 9, tzinfo=UTC)

    app_a = await _new_application(db_session)
    req_a = await _make_request(db_session, application_id=app_a.id)
    await _confirmed_slot(db_session, request=req_a, starts_at=start)
    await db_session.flush()

    app_b = await _new_application(db_session)
    req_b = await _make_request(db_session, application_id=app_b.id)
    # starts exactly when the first ends — half-open range, no overlap
    await _confirmed_slot(
        db_session, request=req_b, starts_at=start + timedelta(minutes=45)
    )
    await db_session.flush()  # must not raise


async def test_unselected_overlapping_slots_are_allowed(db_session):
    """Only *confirmed* (selected_at IS NOT NULL) slots are constrained —
    several unselected offers may legitimately overlap until one is chosen."""
    start = datetime(2026, 12, 1, 9, tzinfo=UTC)

    app_a = await _new_application(db_session)
    req_a = await _make_request(db_session, application_id=app_a.id)
    db_session.add(
        InterviewSlot(
            id=uuid.uuid4(),
            request_id=req_a.id,
            starts_at=start,
            ends_at=start + timedelta(minutes=45),
        )
    )
    await db_session.flush()

    app_b = await _new_application(db_session)
    req_b = await _make_request(db_session, application_id=app_b.id)
    db_session.add(
        InterviewSlot(
            id=uuid.uuid4(),
            request_id=req_b.id,
            starts_at=start + timedelta(minutes=10),
            ends_at=start + timedelta(minutes=55),
        )
    )
    await db_session.flush()  # must not raise — neither is selected
