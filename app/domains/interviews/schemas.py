import uuid
from datetime import UTC, date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domains.interviews.enums import InterviewMode

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _hhmm_to_minutes(value: str) -> int:
    try:
        h, m = (int(p) for p in value.split(":"))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"'{value}' is not a HH:MM time") from exc
    if not (0 <= h <= 24 and 0 <= m < 60):
        raise ValueError(f"'{value}' is out of range")
    total = h * 60 + m
    # 24:00 is the valid end-of-day sentinel; 24:01–24:59 are not real times
    # and exceed the DB's end_minute <= 1440 constraint.
    if total > 1440:
        raise ValueError(f"'{value}' is past the end of the day (max 24:00)")
    return total


def _minutes_to_hhmm(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


# --------------------------------------------------------------------- scheduling


class InterviewSlotIn(BaseModel):
    starts_at: datetime


class InterviewRequestIn(BaseModel):
    mode: InterviewMode
    location_or_link: str | None = None
    duration_minutes: int = Field(default=45, ge=5, le=480)
    notes: str | None = None
    # Empty = the candidate self-books from interview availability; non-empty =
    # HR hand-picked these specific times.
    slots: list[InterviewSlotIn] = Field(default_factory=list, max_length=20)

    @field_validator("location_or_link", "notes", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("slots")
    @classmethod
    def _dedupe_and_require_future(
        cls, slots: list[InterviewSlotIn]
    ) -> list[InterviewSlotIn]:
        now = datetime.now(UTC)
        seen: set[datetime] = set()
        unique: list[InterviewSlotIn] = []
        for slot in slots:
            when = slot.starts_at
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            if when <= now:
                raise ValueError(f"Interview slot '{when.isoformat()}' is in the past")
            if when in seen:
                continue
            seen.add(when)
            unique.append(InterviewSlotIn(starts_at=when))
        if slots and not unique:
            raise ValueError("At least one distinct time slot is required")
        return sorted(unique, key=lambda s: s.starts_at)


class SelectSlotIn(BaseModel):
    """Confirm an interview time — either an existing hand-picked slot
    (`slot_id`) or an open availability instant (`starts_at`)."""

    slot_id: uuid.UUID | None = None
    starts_at: datetime | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "SelectSlotIn":
        if (self.slot_id is None) == (self.starts_at is None):
            raise ValueError("Provide exactly one of slot_id or starts_at")
        return self


class InterviewSlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    selected: bool


class InterviewRequestOut(BaseModel):
    id: uuid.UUID
    application_id: uuid.UUID
    mode: str
    location_or_link: str | None
    duration_minutes: int
    notes: str | None
    self_scheduled: bool
    created_at: datetime
    slots: list[InterviewSlotOut]
    selected_slot_id: uuid.UUID | None
    selected_at: datetime | None


class InterviewStatusOut(BaseModel):
    """Per-application interview progress for the HR pipeline view."""

    application_id: uuid.UUID
    state: Literal["awaiting", "confirmed"]
    starts_at: datetime | None = None


class UpcomingInterviewOut(BaseModel):
    application_id: uuid.UUID
    applicant_name: str
    job_title: str
    mode: str
    location_or_link: str | None
    starts_at: datetime
    ends_at: datetime


# ------------------------------------------------------------------- availability


class AvailabilityWindowIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start: str  # "HH:MM"
    end: str  # "HH:MM"

    @field_validator("start", "end")
    @classmethod
    def _valid_time(cls, v: str) -> str:
        _hhmm_to_minutes(v)
        return v


class AvailabilityWindowOut(BaseModel):
    weekday: int
    start: str
    end: str


class InterviewConfigIn(BaseModel):
    slot_minutes: int = Field(ge=5, le=480)
    horizon_days: int = Field(ge=1, le=120)
    min_notice_hours: int = Field(ge=0, le=336)
    timezone: str

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"'{v}' is not a known IANA timezone") from exc
        return v


class InterviewConfigOut(BaseModel):
    slot_minutes: int
    horizon_days: int
    min_notice_hours: int
    timezone: str


class DateOverrideIn(BaseModel):
    """A single-day or date-range exception. ``is_unavailable`` blocks the days
    entirely; otherwise ``start``/``end`` (HH:MM) replace that day's weekly
    windows."""

    start_date: date
    end_date: date | None = None
    is_unavailable: bool = True
    start: str | None = None  # "HH:MM"
    end: str | None = None  # "HH:MM"
    note: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check(self) -> "DateOverrideIn":
        self.end_date = self.end_date or self.start_date
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.is_unavailable:
            self.start = self.end = None
        else:
            if not self.start or not self.end:
                raise ValueError("a custom-hours override needs a start and end")
            if _hhmm_to_minutes(self.end) <= _hhmm_to_minutes(self.start):
                raise ValueError("override end time must be after its start")
        self.note = (self.note or "").strip() or None
        return self


class DateOverrideOut(BaseModel):
    id: uuid.UUID
    start_date: date
    end_date: date
    is_unavailable: bool
    start: str | None
    end: str | None
    note: str | None


class GlobalAvailabilityIn(BaseModel):
    config: InterviewConfigIn
    windows: list[AvailabilityWindowIn] = Field(default_factory=list, max_length=60)


class GlobalAvailabilityOut(BaseModel):
    config: InterviewConfigOut
    windows: list[AvailabilityWindowOut]
    overrides: list[DateOverrideOut]


class DateOverridesIn(BaseModel):
    """The full set of global date overrides — a whole-list replace, so the
    dedicated overrides page (and its CSV import) sends everything at once."""

    overrides: list[DateOverrideIn] = Field(default_factory=list, max_length=365)


class JobPostAvailabilityIn(BaseModel):
    # An empty windows list means "use the global calendar for this job post".
    windows: list[AvailabilityWindowIn] = Field(default_factory=list, max_length=60)
    interviewer_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class InterviewerOut(BaseModel):
    id: uuid.UUID
    first_name: str
    last_name: str
    email: str


class JobPostAvailabilityOut(BaseModel):
    uses_custom_windows: bool
    windows: list[AvailabilityWindowOut]  # effective (custom if any, else global)
    interviewers: list[InterviewerOut]
    config: InterviewConfigOut


class OpenSlotOut(BaseModel):
    starts_at: datetime
    ends_at: datetime
