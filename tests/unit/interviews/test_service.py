"""Mock-repository unit tests for the F07 entities/repository conversion —
delegation and the IntegrityError -> SlotUnavailableError wiring. The actual
booking/overlap/race behavior is covered end-to-end against a real database
in tests/integration/test_interview_service.py; these just prove the service
still calls the right repository methods and still translates a race the
same way now that it goes through `UnitOfWork` instead of a raw session.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.interviews import entities
from app.domains.interviews.exceptions import (
    InterviewRequestNotFoundError,
    SlotUnavailableError,
)
from app.domains.interviews.scheduling_service import InterviewService
from app.domains.interviews.schemas import SelectSlotIn


def make_service():
    interviews = AsyncMock()
    availability = AsyncMock()
    uow = AsyncMock()
    return (
        InterviewService(interviews, availability, uow),
        interviews,
        availability,
        uow,
    )


def make_request(*, slots=None, self_scheduled=False, duration_minutes=45):
    return entities.InterviewRequest(
        id=uuid.uuid4(),
        application_id=uuid.uuid4(),
        created_by_user_id=uuid.uuid4(),
        mode="video",
        duration_minutes=duration_minutes,
        self_scheduled=self_scheduled,
        slots=slots or [],
    )


class TestSelectSlot:
    async def test_raises_when_no_request_exists(self):
        service, interviews, _availability, _uow = make_service()
        interviews.get_application.return_value = AsyncMock(status="interview")
        interviews.get_request_with_slots.return_value = None

        with pytest.raises(InterviewRequestNotFoundError):
            await service.select_slot(
                uuid.uuid4(),
                SelectSlotIn(slot_id=uuid.uuid4()),
                selected_by_user_id=uuid.uuid4(),
            )

    async def test_integrity_error_on_commit_becomes_slot_unavailable(self):
        service, interviews, _availability, uow = make_service()
        future = datetime.now(UTC) + timedelta(days=2)
        slot = entities.InterviewSlot(
            id=uuid.uuid4(), request_id=uuid.uuid4(), starts_at=future, ends_at=future
        )
        request = make_request(slots=[slot])
        interviews.get_application.return_value = AsyncMock(status="interview")
        interviews.get_request_with_slots.return_value = request
        interviews.overlaps_confirmed.return_value = False
        uow.commit.side_effect = IntegrityError("stmt", {}, Exception("boom"))

        with pytest.raises(SlotUnavailableError):
            await service.select_slot(
                uuid.uuid4(),
                SelectSlotIn(slot_id=slot.id),
                selected_by_user_id=uuid.uuid4(),
            )

        uow.rollback.assert_called_once()
        interviews.sync_slot_selections.assert_called_once()


class TestApplicationsAwaitingSlotPick:
    async def test_delegates_to_repository(self):
        service, interviews, _availability, _uow = make_service()
        ids = [uuid.uuid4(), uuid.uuid4()]
        interviews.applications_awaiting_slot_pick.return_value = {ids[0]}

        result = await service.applications_awaiting_slot_pick(ids)

        interviews.applications_awaiting_slot_pick.assert_called_once_with(ids)
        assert result == {ids[0]}


class TestDeleteRequest:
    async def test_deletes_and_commits(self):
        service, interviews, _availability, uow = make_service()
        application_id = uuid.uuid4()

        await service.delete_request(application_id)

        interviews.delete_request.assert_called_once_with(application_id)
        uow.commit.assert_called_once()
