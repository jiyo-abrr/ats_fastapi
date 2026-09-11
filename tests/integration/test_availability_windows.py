"""F24 (rest) — overlapping availability windows on the same weekday are
rejected at authoring time, instead of silently producing duplicate/redundant
generated slots."""

import pytest

from app.core.unit_of_work import UnitOfWork
from app.domains.interviews.availability_repository import (
    InterviewAvailabilityRepository,
)
from app.domains.interviews.availability_service import InterviewAvailabilityService
from app.domains.interviews.exceptions import InvalidAvailabilityWindowError
from app.domains.interviews.schemas import AvailabilityWindowIn, GlobalAvailabilityIn


def _make_service(db_session) -> InterviewAvailabilityService:
    return InterviewAvailabilityService(
        InterviewAvailabilityRepository(db_session), UnitOfWork(db_session)
    )


def _config():
    from app.domains.interviews.schemas import InterviewConfigIn

    return InterviewConfigIn(
        slot_minutes=30, horizon_days=14, min_notice_hours=1, timezone="UTC"
    )


async def test_rejects_overlapping_windows_same_weekday(db_session):
    svc = _make_service(db_session)
    payload = GlobalAvailabilityIn(
        config=_config(),
        windows=[
            AvailabilityWindowIn(weekday=0, start="09:00", end="12:00"),
            AvailabilityWindowIn(weekday=0, start="11:00", end="13:00"),
        ],
    )
    with pytest.raises(InvalidAvailabilityWindowError):
        await svc.set_global(payload)


async def test_allows_back_to_back_windows_same_weekday(db_session):
    svc = _make_service(db_session)
    payload = GlobalAvailabilityIn(
        config=_config(),
        windows=[
            AvailabilityWindowIn(weekday=0, start="09:00", end="12:00"),
            AvailabilityWindowIn(weekday=0, start="12:00", end="15:00"),
        ],
    )
    result = await svc.set_global(payload)
    assert len(result.windows) == 2


async def test_allows_overlap_across_different_weekdays(db_session):
    svc = _make_service(db_session)
    payload = GlobalAvailabilityIn(
        config=_config(),
        windows=[
            AvailabilityWindowIn(weekday=0, start="09:00", end="12:00"),
            AvailabilityWindowIn(weekday=1, start="09:00", end="12:00"),
        ],
    )
    result = await svc.set_global(payload)
    assert len(result.windows) == 2
