from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domains.applications.interviews import InterviewRequestIn


def _payload(**over):
    base = dict(
        mode="video",
        location_or_link="https://meet.example/abc",
        duration_minutes=45,
        slots=[{"starts_at": "2026-10-01T09:00:00Z"}],
    )
    base.update(over)
    return InterviewRequestIn(**base)


def test_slots_are_deduped_and_sorted():
    payload = _payload(
        slots=[
            {"starts_at": "2026-10-02T09:00:00Z"},
            {"starts_at": "2026-10-01T09:00:00Z"},
            {"starts_at": "2026-10-02T09:00:00Z"},
        ]
    )
    times = [s.starts_at for s in payload.slots]
    assert times == [
        datetime(2026, 10, 1, 9, tzinfo=UTC),
        datetime(2026, 10, 2, 9, tzinfo=UTC),
    ]


def test_naive_slot_times_are_assumed_utc():
    payload = _payload(slots=[{"starts_at": "2026-10-01T09:00:00"}])
    assert payload.slots[0].starts_at == datetime(2026, 10, 1, 9, tzinfo=UTC)


def test_blank_logistics_become_none():
    payload = _payload(location_or_link="  ", notes="")
    assert payload.location_or_link is None
    assert payload.notes is None


def test_empty_slots_is_self_schedule_mode():
    # No hand-picked times => the candidate self-books from availability.
    payload = _payload(slots=[])
    assert payload.slots == []


def test_duration_bounds_enforced():
    with pytest.raises(ValidationError):
        _payload(duration_minutes=600)


def test_mode_must_be_known():
    with pytest.raises(ValidationError):
        _payload(mode="carrier-pigeon")
