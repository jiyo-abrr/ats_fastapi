"""Plain-dataclass entities for `interviews/` (review F07).

Covers the models `InterviewService`/`InterviewAvailabilityService` actually
construct/mutate: `InterviewConfig`, `AvailabilityWindow`, `DateOverride`,
`InterviewRequest`, `InterviewSlot`. `JobPostInterviewer` (a pure
job_post_id/user_id association row, no other fields) stays a whole-list
replace managed directly by the repository, the same way `job_posts`' own
`job_post_tags`/`job_post_exclusions` join tables have no entity either.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime


@dataclass
class InterviewConfig:
    id: int
    slot_minutes: int
    horizon_days: int
    min_notice_hours: int
    timezone: str
    updated_at: datetime | None = None


@dataclass
class LogisticsPreset:
    """A named, reusable video-call link or on-site address. `job_post_id`
    NULL is the global list."""

    id: uuid.UUID
    job_post_id: uuid.UUID | None
    mode: str  # "video" | "onsite"
    label: str
    value: str | None = None
    # On-site only: an optional link to a `company_addresses` row — see the
    # model docstring for why `value` is ignored in favor of it when set.
    company_address_id: uuid.UUID | None = None
    created_at: datetime | None = None


@dataclass
class AvailabilityWindow:
    id: uuid.UUID
    job_post_id: uuid.UUID | None
    weekday: int
    start_minute: int
    end_minute: int
    created_at: datetime | None = None


@dataclass
class DateOverride:
    id: uuid.UUID
    job_post_id: uuid.UUID | None
    start_date: date
    end_date: date
    is_unavailable: bool
    start_minute: int | None = None
    end_minute: int | None = None
    note: str | None = None
    created_at: datetime | None = None


@dataclass
class InterviewSlot:
    id: uuid.UUID
    request_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    selected_at: datetime | None = None
    created_at: datetime | None = None


@dataclass
class InterviewRequest:
    id: uuid.UUID
    application_id: uuid.UUID
    created_by_user_id: uuid.UUID
    mode: str
    duration_minutes: int
    self_scheduled: bool
    location_or_link: str | None = None
    company_address_id: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    slots: list[InterviewSlot] | None = None
