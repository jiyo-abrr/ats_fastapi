from datetime import date

import pytest
from pydantic import ValidationError

from app.domains.interviews.schemas import (
    AvailabilityWindowIn,
    DateOverrideIn,
    DateOverridesIn,
    GlobalAvailabilityIn,
    InterviewConfigIn,
    _hhmm_to_minutes,
    _minutes_to_hhmm,
)


def _config(**over):
    base = dict(
        slot_minutes=45, horizon_days=21, min_notice_hours=12, timezone="Asia/Manila"
    )
    base.update(over)
    return InterviewConfigIn(**base)


@pytest.mark.parametrize(
    ("text", "minutes"),
    [("00:00", 0), ("09:30", 570), ("17:00", 1020), ("24:00", 1440)],
)
def test_hhmm_roundtrip(text, minutes):
    assert _hhmm_to_minutes(text) == minutes
    if minutes < 1440:
        assert _minutes_to_hhmm(minutes) == text


@pytest.mark.parametrize("bad", ["9", "25:00", "09:60", "abc", ""])
def test_hhmm_rejects_garbage(bad):
    with pytest.raises(ValueError):
        _hhmm_to_minutes(bad)


def test_window_validates_times():
    AvailabilityWindowIn(weekday=0, start="09:00", end="12:00")
    with pytest.raises(ValidationError):
        AvailabilityWindowIn(weekday=0, start="09:00", end="9am")
    with pytest.raises(ValidationError):
        AvailabilityWindowIn(weekday=7, start="09:00", end="12:00")


def test_config_rejects_unknown_timezone():
    with pytest.raises(ValidationError):
        _config(timezone="Middle/Earth")


def test_config_bounds():
    with pytest.raises(ValidationError):
        _config(slot_minutes=0)
    with pytest.raises(ValidationError):
        _config(horizon_days=999)


def test_global_payload_accepts_no_windows():
    payload = GlobalAvailabilityIn(config=_config(), windows=[])
    assert payload.windows == []


def test_blackout_override_defaults_end_date_and_clears_hours():
    ov = DateOverrideIn(start_date=date(2026, 12, 25), start="09:00", end="17:00")
    assert ov.is_unavailable is True
    assert ov.end_date == date(2026, 12, 25)
    assert ov.start is None and ov.end is None


def test_custom_hours_override_requires_valid_times():
    ov = DateOverrideIn(
        start_date=date(2026, 12, 24),
        is_unavailable=False,
        start="09:00",
        end="12:00",
    )
    assert ov.start == "09:00"
    with pytest.raises(ValidationError):
        DateOverrideIn(
            start_date=date(2026, 12, 24), is_unavailable=False, start="09:00"
        )
    with pytest.raises(ValidationError):
        DateOverrideIn(
            start_date=date(2026, 12, 24),
            is_unavailable=False,
            start="12:00",
            end="09:00",
        )


def test_date_overrides_payload_defaults_to_empty():
    assert DateOverridesIn().overrides == []


def test_date_overrides_payload_validates_each_row():
    with pytest.raises(ValidationError):
        DateOverridesIn(
            overrides=[
                {"start_date": "2026-12-25"},
                {"start_date": "2026-12-24", "is_unavailable": False},  # no hours
            ]
        )


def test_override_range_must_not_invert():
    with pytest.raises(ValidationError):
        DateOverrideIn(start_date=date(2026, 12, 25), end_date=date(2026, 12, 20))
