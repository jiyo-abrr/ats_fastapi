"""F23 (rest) — end-to-end InterviewService tests against a real database.
Previously this domain had schema-level tests only; these exercise the actual
booking flow (manual offer -> confirm, self-schedule, idempotent
re-confirmation, past-slot / wrong-mode rejection)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.unit_of_work import UnitOfWork
from app.domains.interviews.availability_repository import (
    InterviewAvailabilityRepository,
)
from app.domains.interviews.availability_service import InterviewAvailabilityService
from app.domains.interviews.exceptions import (
    ApplicationNotInInterviewError,
    SlotNotOnRequestError,
    SlotUnavailableError,
)
from app.domains.interviews.repository import InterviewRepository
from app.domains.interviews.scheduling_service import InterviewService
from app.domains.interviews.schemas import (
    InterviewRequestIn,
    InterviewSlotIn,
    SelectSlotIn,
)
from tests.integration.factories import make_application, make_job_post, make_user


def _make_service(db_session) -> InterviewService:
    uow = UnitOfWork(db_session)
    availability = InterviewAvailabilityService(
        InterviewAvailabilityRepository(db_session), uow
    )
    return InterviewService(InterviewRepository(db_session), availability, uow)


async def _interview_stage_application(db_session):
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session, role="applicant")
    hr = await make_user(db_session, role="hr")
    app = await make_application(
        db_session, job_post=jp, applicant=applicant, status="interview"
    )
    await db_session.commit()
    return app, applicant, hr


def _future(**kw) -> datetime:
    return datetime.now(UTC) + timedelta(**kw)


async def test_requires_application_in_interview_stage(db_session):
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session, role="applicant")
    hr = await make_user(db_session, role="hr")
    app = await make_application(
        db_session, job_post=jp, applicant=applicant, status="applied"
    )
    await db_session.commit()

    svc = _make_service(db_session)
    with pytest.raises(ApplicationNotInInterviewError):
        await svc.set_request(
            app.id,
            InterviewRequestIn(mode="video", slots=[]),
            created_by_user_id=hr.id,
        )


async def test_manual_offer_then_confirm_by_slot_id(db_session):
    app, applicant, hr = await _interview_stage_application(db_session)
    svc = _make_service(db_session)

    slot_a = _future(days=2, hours=1)
    slot_b = _future(days=2, hours=3)
    request = await svc.set_request(
        app.id,
        InterviewRequestIn(
            mode="video",
            slots=[
                InterviewSlotIn(starts_at=slot_a),
                InterviewSlotIn(starts_at=slot_b),
            ],
        ),
        created_by_user_id=hr.id,
    )
    assert request.self_scheduled is False
    assert len(request.slots) == 2

    chosen = next(s for s in request.slots if s.starts_at == slot_a)
    confirmed = await svc.select_slot(
        app.id, SelectSlotIn(slot_id=chosen.id), selected_by_user_id=applicant.id
    )
    assert confirmed.selected_slot_id == chosen.id


async def test_manual_offer_rejects_arbitrary_time(db_session):
    """A manual (hand-picked) offer is restrictive — the applicant can't pick
    an arbitrary open-availability instant instead of one of the offers."""
    app, applicant, hr = await _interview_stage_application(db_session)
    svc = _make_service(db_session)
    await svc.set_request(
        app.id,
        InterviewRequestIn(
            mode="video", slots=[InterviewSlotIn(starts_at=_future(days=2))]
        ),
        created_by_user_id=hr.id,
    )

    with pytest.raises(SlotNotOnRequestError):
        await svc.select_slot(
            app.id,
            SelectSlotIn(starts_at=_future(days=3)),
            selected_by_user_id=applicant.id,
        )


async def test_rejects_confirming_a_past_slot(db_session):
    """`InterviewRequestIn` itself rejects past slots on input — this proves
    a slot that has *since* passed (offered for tomorrow, confirmed a day
    late) is also rejected at selection time."""
    app, applicant, hr = await _interview_stage_application(db_session)
    svc = _make_service(db_session)
    request = await svc.set_request(
        app.id,
        InterviewRequestIn(
            mode="video", slots=[InterviewSlotIn(starts_at=_future(minutes=5))]
        ),
        created_by_user_id=hr.id,
    )
    slot_id = request.slots[0].id

    # Simulate time passing: move the slot into the past directly.
    from sqlalchemy import update

    from app.domains.interviews.models import InterviewSlot

    await db_session.execute(
        update(InterviewSlot)
        .where(InterviewSlot.id == slot_id)
        .values(starts_at=datetime.now(UTC) - timedelta(minutes=1))
    )
    await db_session.flush()

    with pytest.raises(SlotUnavailableError):
        await svc.select_slot(
            app.id,
            SelectSlotIn(slot_id=slot_id),
            selected_by_user_id=applicant.id,
        )


async def test_reconfirming_the_same_slot_is_idempotent(db_session):
    app, applicant, hr = await _interview_stage_application(db_session)
    svc = _make_service(db_session)
    request = await svc.set_request(
        app.id,
        InterviewRequestIn(
            mode="video", slots=[InterviewSlotIn(starts_at=_future(days=2))]
        ),
        created_by_user_id=hr.id,
    )
    slot_id = request.slots[0].id

    first = await svc.select_slot(
        app.id, SelectSlotIn(slot_id=slot_id), selected_by_user_id=applicant.id
    )
    second = await svc.select_slot(
        app.id, SelectSlotIn(slot_id=slot_id), selected_by_user_id=applicant.id
    )
    assert first.selected_slot_id == second.selected_slot_id == slot_id


async def test_reselecting_a_different_slot_replaces_the_confirmation(db_session):
    """Regression: `ux_interview_slots_one_selected` is a partial unique
    *index*, not a deferrable constraint — Postgres checks it per statement.
    Clearing the old selection and setting the new one must not both land in
    the DB with the new one visible before the old one is cleared, or this
    (a candidate simply changing their mind about the time) fails with a
    spurious "just taken" on every attempt, not just a real race."""
    app, applicant, hr = await _interview_stage_application(db_session)
    svc = _make_service(db_session)
    slot_a = _future(days=2, hours=1)
    slot_b = _future(days=2, hours=3)
    request = await svc.set_request(
        app.id,
        InterviewRequestIn(
            mode="video",
            slots=[
                InterviewSlotIn(starts_at=slot_a),
                InterviewSlotIn(starts_at=slot_b),
            ],
        ),
        created_by_user_id=hr.id,
    )
    id_a = next(s.id for s in request.slots if s.starts_at == slot_a)
    id_b = next(s.id for s in request.slots if s.starts_at == slot_b)

    await svc.select_slot(
        app.id, SelectSlotIn(slot_id=id_a), selected_by_user_id=applicant.id
    )
    changed = await svc.select_slot(
        app.id, SelectSlotIn(slot_id=id_b), selected_by_user_id=applicant.id
    )
    assert changed.selected_slot_id == id_b


async def test_editing_duration_keeps_ends_at_in_sync(db_session):
    """review F03: editing an offer's duration must update every slot's
    ends_at too, or the DB-enforced non-overlap constraint would use a stale
    range."""
    app, applicant, hr = await _interview_stage_application(db_session)
    svc = _make_service(db_session)
    start = _future(days=2)
    await svc.set_request(
        app.id,
        InterviewRequestIn(
            mode="video", duration_minutes=30, slots=[InterviewSlotIn(starts_at=start)]
        ),
        created_by_user_id=hr.id,
    )
    updated = await svc.set_request(
        app.id,
        InterviewRequestIn(
            mode="video", duration_minutes=90, slots=[InterviewSlotIn(starts_at=start)]
        ),
        created_by_user_id=hr.id,
    )
    assert updated.slots[0].ends_at == start + timedelta(minutes=90)


async def test_ensure_default_request_auto_provisions_self_schedule(db_session):
    """The candidate must have times to pick from the moment an application
    enters the interview stage — no separate "open the interview" step."""
    app, applicant, hr = await _interview_stage_application(db_session)
    svc = _make_service(db_session)

    request = await svc.ensure_default_request(app.id, created_by_user_id=hr.id)

    assert request.mode == "video"
    assert request.self_scheduled is True
    assert request.slots == []
    assert request.duration_minutes > 0


async def test_ensure_default_request_is_a_noop_when_hr_already_set_one_up(
    db_session,
):
    """HR hand-picking times before/while the status moves must not be
    clobbered by the auto-provisioned default."""
    app, applicant, hr = await _interview_stage_application(db_session)
    svc = _make_service(db_session)
    slot = _future(days=3)
    manual = await svc.set_request(
        app.id,
        InterviewRequestIn(
            mode="onsite",
            location_or_link="HQ, 4F",
            slots=[InterviewSlotIn(starts_at=slot)],
        ),
        created_by_user_id=hr.id,
    )

    result = await svc.ensure_default_request(app.id, created_by_user_id=hr.id)

    assert result.id == manual.id
    assert result.mode == "onsite"
    assert result.self_scheduled is False
    assert len(result.slots) == 1
