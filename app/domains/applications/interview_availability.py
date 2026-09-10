"""Interview availability — the recurring weekly windows candidates self-book
interviews into.

Two scopes:
- **global** (`job_post_id IS NULL`) — the default, edited on the `/calendar` page.
- **per job post** — that post's own windows, which fully replace the global set
  for its applicants. A post with no rules of its own falls back to global.

`InterviewConfig` (a single row) holds the booking rules — slot length, how far
ahead, minimum notice, and the timezone the wall-clock window times are in.
`open_slots_for_application` expands the resolved windows into concrete UTC
instants, dropping ones that are too soon or already booked by anyone.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.models import (
    Application,
    InterviewAvailabilityRule,
    InterviewConfig,
    InterviewDateOverride,
    InterviewRequest,
    InterviewSlot,
    JobPostInterviewer,
)
from app.domains.auth.models import User
from app.domains.job_posts.models import JobPost
from app.domains.rbac.models import Role

_CONFIG_ID = 1
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# --------------------------------------------------------------------------- IO


def _hhmm_to_minutes(value: str) -> int:
    try:
        h, m = (int(p) for p in value.split(":"))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"'{value}' is not a HH:MM time") from exc
    if not (0 <= h <= 24 and 0 <= m < 60):
        raise ValueError(f"'{value}' is out of range")
    return h * 60 + m


def _minutes_to_hhmm(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


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


# ---------------------------------------------------------------------- service


class InterviewAvailabilityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # -- config ------------------------------------------------------------

    async def _get_or_make_config(self) -> InterviewConfig:
        config = await self.db.get(InterviewConfig, _CONFIG_ID)
        if config is None:
            config = InterviewConfig(id=_CONFIG_ID)
            self.db.add(config)
            await self.db.flush()
        return config

    @staticmethod
    def _config_out(config: InterviewConfig) -> InterviewConfigOut:
        return InterviewConfigOut(
            slot_minutes=config.slot_minutes,
            horizon_days=config.horizon_days,
            min_notice_hours=config.min_notice_hours,
            timezone=config.timezone,
        )

    # -- window rows -----------------------------------------------------

    async def _windows(
        self, job_post_id: uuid.UUID | None
    ) -> list[InterviewAvailabilityRule]:
        stmt = select(InterviewAvailabilityRule).order_by(
            InterviewAvailabilityRule.weekday,
            InterviewAvailabilityRule.start_minute,
        )
        stmt = (
            stmt.where(InterviewAvailabilityRule.job_post_id.is_(None))
            if job_post_id is None
            else stmt.where(InterviewAvailabilityRule.job_post_id == job_post_id)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    @staticmethod
    def _windows_out(
        rules: list[InterviewAvailabilityRule],
    ) -> list[AvailabilityWindowOut]:
        return [
            AvailabilityWindowOut(
                weekday=r.weekday,
                start=_minutes_to_hhmm(r.start_minute),
                end=_minutes_to_hhmm(r.end_minute),
            )
            for r in rules
        ]

    async def _replace_windows(
        self,
        job_post_id: uuid.UUID | None,
        windows: list[AvailabilityWindowIn],
    ) -> None:
        clause = (
            InterviewAvailabilityRule.job_post_id.is_(None)
            if job_post_id is None
            else InterviewAvailabilityRule.job_post_id == job_post_id
        )
        await self.db.execute(delete(InterviewAvailabilityRule).where(clause))
        for window in windows:
            start = _hhmm_to_minutes(window.start)
            end = _hhmm_to_minutes(window.end)
            if end <= start:
                raise ValidationError(
                    f"{_WEEKDAYS[window.weekday]} window end must be after its start"
                )
            self.db.add(
                InterviewAvailabilityRule(
                    id=uuid.uuid4(),
                    job_post_id=job_post_id,
                    weekday=window.weekday,
                    start_minute=start,
                    end_minute=end,
                )
            )

    # -- date overrides ------------------------------------------------

    async def _overrides(
        self, job_post_id: uuid.UUID | None
    ) -> list[InterviewDateOverride]:
        clause = (
            InterviewDateOverride.job_post_id.is_(None)
            if job_post_id is None
            else InterviewDateOverride.job_post_id == job_post_id
        )
        stmt = (
            select(InterviewDateOverride)
            .where(clause)
            .order_by(InterviewDateOverride.start_date)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    @staticmethod
    def _overrides_out(
        rows: list[InterviewDateOverride],
    ) -> list[DateOverrideOut]:
        return [
            DateOverrideOut(
                id=o.id,
                start_date=o.start_date,
                end_date=o.end_date,
                is_unavailable=o.is_unavailable,
                start=(
                    None
                    if o.start_minute is None
                    else _minutes_to_hhmm(o.start_minute)
                ),
                end=(
                    None if o.end_minute is None else _minutes_to_hhmm(o.end_minute)
                ),
                note=o.note,
            )
            for o in rows
        ]

    async def _replace_overrides(
        self,
        job_post_id: uuid.UUID | None,
        overrides: list[DateOverrideIn],
    ) -> None:
        clause = (
            InterviewDateOverride.job_post_id.is_(None)
            if job_post_id is None
            else InterviewDateOverride.job_post_id == job_post_id
        )
        await self.db.execute(delete(InterviewDateOverride).where(clause))
        for ov in overrides:
            self.db.add(
                InterviewDateOverride(
                    id=uuid.uuid4(),
                    job_post_id=job_post_id,
                    start_date=ov.start_date,
                    end_date=ov.end_date,
                    is_unavailable=ov.is_unavailable,
                    start_minute=(
                        None if ov.start is None else _hhmm_to_minutes(ov.start)
                    ),
                    end_minute=(
                        None if ov.end is None else _hhmm_to_minutes(ov.end)
                    ),
                    note=ov.note,
                )
            )

    # -- global --------------------------------------------------------

    async def get_global(self) -> GlobalAvailabilityOut:
        config = await self._get_or_make_config()
        return GlobalAvailabilityOut(
            config=self._config_out(config),
            windows=self._windows_out(await self._windows(None)),
            overrides=self._overrides_out(await self._overrides(None)),
        )

    async def set_global(self, payload: GlobalAvailabilityIn) -> GlobalAvailabilityOut:
        config = await self._get_or_make_config()
        config.slot_minutes = payload.config.slot_minutes
        config.horizon_days = payload.config.horizon_days
        config.min_notice_hours = payload.config.min_notice_hours
        config.timezone = payload.config.timezone
        await self._replace_windows(None, payload.windows)
        await self.db.commit()
        return await self.get_global()

    # -- global date overrides (dedicated page) -----------------------

    async def get_overrides(self) -> list[DateOverrideOut]:
        return self._overrides_out(await self._overrides(None))

    async def set_overrides(
        self, payload: DateOverridesIn
    ) -> list[DateOverrideOut]:
        await self._replace_overrides(None, payload.overrides)
        await self.db.commit()
        return await self.get_overrides()

    # -- per job post -------------------------------------------------

    async def list_staff(self) -> list[InterviewerOut]:
        """Every admin / HR account — the pool for a job post's interviewer
        list. Accessible to any `manage_applications` user (unlike the
        admin-only `/auth/users` list)."""
        rows = (
            (
                await self.db.execute(
                    select(User)
                    .join(Role, Role.id == User.role_id)
                    .where(Role.name.in_(["admin", "hr"]), User.is_active)
                    .order_by(User.first_name, User.last_name)
                )
            )
            .scalars()
            .all()
        )
        return [
            InterviewerOut(
                id=u.id,
                first_name=u.first_name,
                last_name=u.last_name,
                email=u.email,
            )
            for u in rows
        ]

    async def _require_job_post(self, job_post_id: uuid.UUID) -> JobPost:
        job_post = await self.db.get(JobPost, job_post_id)
        if job_post is None:
            raise NotFoundError(f"Job post '{job_post_id}' not found")
        return job_post

    async def _interviewers(self, job_post_id: uuid.UUID) -> list[InterviewerOut]:
        rows = (
            (
                await self.db.execute(
                    select(User)
                    .join(
                        JobPostInterviewer,
                        JobPostInterviewer.user_id == User.id,
                    )
                    .where(JobPostInterviewer.job_post_id == job_post_id)
                    .order_by(User.first_name, User.last_name)
                )
            )
            .scalars()
            .all()
        )
        return [
            InterviewerOut(
                id=u.id,
                first_name=u.first_name,
                last_name=u.last_name,
                email=u.email,
            )
            for u in rows
        ]

    async def get_for_job_post(self, job_post_id: uuid.UUID) -> JobPostAvailabilityOut:
        await self._require_job_post(job_post_id)
        config = await self._get_or_make_config()
        custom = await self._windows(job_post_id)
        effective = custom if custom else await self._windows(None)
        return JobPostAvailabilityOut(
            uses_custom_windows=bool(custom),
            windows=self._windows_out(effective),
            interviewers=await self._interviewers(job_post_id),
            config=self._config_out(config),
        )

    async def set_for_job_post(
        self, job_post_id: uuid.UUID, payload: JobPostAvailabilityIn
    ) -> JobPostAvailabilityOut:
        await self._require_job_post(job_post_id)
        await self._replace_windows(job_post_id, payload.windows)

        await self.db.execute(
            delete(JobPostInterviewer).where(
                JobPostInterviewer.job_post_id == job_post_id
            )
        )
        if payload.interviewer_ids:
            valid = set(
                (
                    await self.db.execute(
                        select(User.id).where(User.id.in_(payload.interviewer_ids))
                    )
                )
                .scalars()
                .all()
            )
            for user_id in dict.fromkeys(payload.interviewer_ids):
                if user_id not in valid:
                    raise ValidationError(f"User '{user_id}' does not exist")
                self.db.add(
                    JobPostInterviewer(
                        id=uuid.uuid4(),
                        job_post_id=job_post_id,
                        user_id=user_id,
                    )
                )
        await self.db.commit()
        return await self.get_for_job_post(job_post_id)

    # -- slot generation --------------------------------------------

    async def _resolved_windows(
        self, job_post_id: uuid.UUID
    ) -> list[InterviewAvailabilityRule]:
        custom = await self._windows(job_post_id)
        return custom if custom else await self._windows(None)

    async def _booked_intervals(
        self, exclude_request_id: uuid.UUID | None
    ) -> list[tuple[datetime, int]]:
        """`(start, duration_minutes)` for every confirmed interview across the
        org — used to block times that overlap an existing booking, not just
        exact-instant clashes."""
        stmt = (
            select(InterviewSlot.starts_at, InterviewRequest.duration_minutes)
            .join(
                InterviewRequest,
                InterviewRequest.id == InterviewSlot.request_id,
            )
            .where(InterviewSlot.selected_at.is_not(None))
        )
        if exclude_request_id is not None:
            stmt = stmt.where(InterviewSlot.request_id != exclude_request_id)
        return [(row[0], row[1]) for row in (await self.db.execute(stmt)).all()]

    async def open_slots_for_application(
        self, application_id: uuid.UUID
    ) -> list[OpenSlotOut]:
        application = await self.db.get(Application, application_id)
        if application is None:
            raise NotFoundError(f"Application '{application_id}' not found")
        if application.status != ApplicationStatus.INTERVIEW.value:
            raise ConflictError(
                "Interview scheduling is only available while the application "
                f"is in the interview stage (currently '{application.status}')"
            )

        request = (
            await self.db.execute(
                select(InterviewRequest).where(
                    InterviewRequest.application_id == application_id
                )
            )
        ).scalar_one_or_none()
        duration = request.duration_minutes if request else None

        config = await self._get_or_make_config()
        step = duration or config.slot_minutes
        try:
            tz = ZoneInfo(config.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            tz = UTC

        rules = await self._resolved_windows(application.job_post_id)
        overrides = await self._overrides(None)
        if not rules and not overrides:
            return []
        by_weekday: dict[int, list[InterviewAvailabilityRule]] = {}
        for rule in rules:
            by_weekday.setdefault(rule.weekday, []).append(rule)

        def windows_for(day: date) -> list[tuple[int, int]]:
            """(start_minute, end_minute) pairs bookable on this calendar date,
            after applying any date override."""
            matched = [
                o for o in overrides if o.start_date <= day <= o.end_date
            ]
            if any(o.is_unavailable for o in matched):
                return []
            custom = [
                (o.start_minute, o.end_minute)
                for o in matched
                if o.start_minute is not None and o.end_minute is not None
            ]
            if custom:
                return custom
            return [
                (r.start_minute, r.end_minute)
                for r in by_weekday.get(day.weekday(), [])
            ]

        now = datetime.now(UTC)
        earliest = now + timedelta(hours=config.min_notice_hours)
        booked = await self._booked_intervals(request.id if request else None)

        def overlaps_booked(start: datetime) -> bool:
            end = start + timedelta(minutes=step)
            return any(
                start < b_start + timedelta(minutes=b_minutes) and end > b_start
                for b_start, b_minutes in booked
            )

        today_local = now.astimezone(tz).date()
        out: list[OpenSlotOut] = []
        for day_offset in range(config.horizon_days + 1):
            day = today_local + timedelta(days=day_offset)
            for start_minute, end_minute in windows_for(day):
                cursor = start_minute
                while cursor + step <= end_minute:
                    local_start = datetime(
                        day.year,
                        day.month,
                        day.day,
                        cursor // 60,
                        cursor % 60,
                        tzinfo=tz,
                    )
                    start_utc = local_start.astimezone(UTC)
                    cursor += step
                    if start_utc < earliest or overlaps_booked(start_utc):
                        continue
                    out.append(
                        OpenSlotOut(
                            starts_at=start_utc,
                            ends_at=start_utc + timedelta(minutes=step),
                        )
                    )
        out.sort(key=lambda s: s.starts_at)
        return out
