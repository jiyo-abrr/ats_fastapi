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

import itertools
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.unit_of_work import UnitOfWork
from app.domains.applications.enums import ApplicationStatus
from app.domains.interviews import entities
from app.domains.interviews.availability_repository import (
    InterviewAvailabilityRepository,
)
from app.domains.interviews.exceptions import (
    ApplicationNotInInterviewError,
    InterviewApplicationNotFoundError,
    InterviewJobPostNotFoundError,
    InvalidAvailabilityWindowError,
    UnknownInterviewerError,
)
from app.domains.interviews.schemas import (
    _WEEKDAYS,
    AvailabilityWindowIn,
    AvailabilityWindowOut,
    DateOverrideIn,
    DateOverrideOut,
    DateOverridesIn,
    GlobalAvailabilityIn,
    GlobalAvailabilityOut,
    InterviewConfigOut,
    InterviewerOut,
    JobPostAvailabilityIn,
    JobPostAvailabilityOut,
    OpenSlotOut,
    _hhmm_to_minutes,
    _minutes_to_hhmm,
)


class InterviewAvailabilityService:
    def __init__(self, availability: InterviewAvailabilityRepository, uow: UnitOfWork):
        self.availability = availability
        self.uow = uow

    # -- config ------------------------------------------------------------

    @staticmethod
    def _config_out(config: entities.InterviewConfig) -> InterviewConfigOut:
        return InterviewConfigOut(
            slot_minutes=config.slot_minutes,
            horizon_days=config.horizon_days,
            min_notice_hours=config.min_notice_hours,
            timezone=config.timezone,
        )

    # -- window rows -----------------------------------------------------

    @staticmethod
    def _windows_out(
        rules: list[entities.AvailabilityWindow],
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
        # Reject overlapping windows on the same weekday up front — slot
        # generation would otherwise silently emit duplicate/redundant
        # instants for the overlap (review F24). Two windows that merely touch
        # (one ends exactly when the other starts) are fine.
        by_weekday: dict[int, list[tuple[int, int]]] = {}
        for window in windows:
            start = _hhmm_to_minutes(window.start)
            end = _hhmm_to_minutes(window.end)
            if end <= start:
                raise InvalidAvailabilityWindowError(
                    f"{_WEEKDAYS[window.weekday]} window end must be after its start"
                )
            by_weekday.setdefault(window.weekday, []).append((start, end))
        for weekday, spans in by_weekday.items():
            for (s1, e1), (s2, e2) in itertools.combinations(sorted(spans), 2):
                if s2 < e1:
                    raise InvalidAvailabilityWindowError(
                        f"{_WEEKDAYS[weekday]} has overlapping windows "
                        f"({_minutes_to_hhmm(s1)}-{_minutes_to_hhmm(e1)} and "
                        f"{_minutes_to_hhmm(s2)}-{_minutes_to_hhmm(e2)})"
                    )

        entities_list = [
            entities.AvailabilityWindow(
                id=uuid.uuid4(),
                job_post_id=job_post_id,
                weekday=window.weekday,
                start_minute=_hhmm_to_minutes(window.start),
                end_minute=_hhmm_to_minutes(window.end),
            )
            for window in windows
        ]
        await self.availability.replace_windows(job_post_id, entities_list)

    # -- date overrides ------------------------------------------------

    @staticmethod
    def _overrides_out(
        rows: list[entities.DateOverride],
    ) -> list[DateOverrideOut]:
        return [
            DateOverrideOut(
                id=o.id,
                start_date=o.start_date,
                end_date=o.end_date,
                is_unavailable=o.is_unavailable,
                start=(
                    None if o.start_minute is None else _minutes_to_hhmm(o.start_minute)
                ),
                end=(None if o.end_minute is None else _minutes_to_hhmm(o.end_minute)),
                note=o.note,
            )
            for o in rows
        ]

    async def _replace_overrides(
        self,
        job_post_id: uuid.UUID | None,
        overrides: list[DateOverrideIn],
    ) -> None:
        entities_list = [
            entities.DateOverride(
                id=uuid.uuid4(),
                job_post_id=job_post_id,
                start_date=ov.start_date,
                end_date=ov.end_date,
                is_unavailable=ov.is_unavailable,
                start_minute=(None if ov.start is None else _hhmm_to_minutes(ov.start)),
                end_minute=(None if ov.end is None else _hhmm_to_minutes(ov.end)),
                note=ov.note,
            )
            for ov in overrides
        ]
        await self.availability.replace_overrides(job_post_id, entities_list)

    # -- global --------------------------------------------------------

    async def get_global(self) -> GlobalAvailabilityOut:
        config = await self.availability.get_or_create_config()
        return GlobalAvailabilityOut(
            config=self._config_out(config),
            windows=self._windows_out(await self.availability.windows(None)),
            overrides=self._overrides_out(await self.availability.overrides(None)),
        )

    async def set_global(self, payload: GlobalAvailabilityIn) -> GlobalAvailabilityOut:
        config = await self.availability.get_or_create_config()
        config.slot_minutes = payload.config.slot_minutes
        config.horizon_days = payload.config.horizon_days
        config.min_notice_hours = payload.config.min_notice_hours
        config.timezone = payload.config.timezone
        await self.availability.save_config(config)
        await self._replace_windows(None, payload.windows)
        await self.uow.commit()
        return await self.get_global()

    # -- global date overrides (dedicated page) -----------------------

    async def get_overrides(self) -> list[DateOverrideOut]:
        return self._overrides_out(await self.availability.overrides(None))

    async def set_overrides(self, payload: DateOverridesIn) -> list[DateOverrideOut]:
        await self._replace_overrides(None, payload.overrides)
        await self.uow.commit()
        return await self.get_overrides()

    # -- per job post -------------------------------------------------

    async def list_staff(self) -> list[InterviewerOut]:
        """Every admin / HR account — the pool for a job post's interviewer
        list. Accessible to any `manage_applications` user (unlike the
        admin-only `/auth/users` list)."""
        rows = await self.availability.list_staff()
        return [
            InterviewerOut(
                id=u.id, first_name=u.first_name, last_name=u.last_name, email=u.email
            )
            for u in rows
        ]

    async def _require_job_post(self, job_post_id: uuid.UUID):
        job_post = await self.availability.get_job_post(job_post_id)
        if job_post is None:
            raise InterviewJobPostNotFoundError(f"Job post '{job_post_id}' not found")
        return job_post

    async def _interviewers(self, job_post_id: uuid.UUID) -> list[InterviewerOut]:
        rows = await self.availability.interviewers(job_post_id)
        return [
            InterviewerOut(
                id=u.id, first_name=u.first_name, last_name=u.last_name, email=u.email
            )
            for u in rows
        ]

    async def get_for_job_post(self, job_post_id: uuid.UUID) -> JobPostAvailabilityOut:
        await self._require_job_post(job_post_id)
        config = await self.availability.get_or_create_config()
        custom = await self.availability.windows(job_post_id)
        effective = custom if custom else await self.availability.windows(None)
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

        interviewer_ids = list(dict.fromkeys(payload.interviewer_ids or []))
        if interviewer_ids:
            valid = await self.availability.valid_user_ids(interviewer_ids)
            for user_id in interviewer_ids:
                if user_id not in valid:
                    raise UnknownInterviewerError(f"User '{user_id}' does not exist")
        await self.availability.replace_interviewers(job_post_id, interviewer_ids)
        await self.uow.commit()
        return await self.get_for_job_post(job_post_id)

    # -- slot generation --------------------------------------------

    async def _resolved_windows(
        self, job_post_id: uuid.UUID
    ) -> list[entities.AvailabilityWindow]:
        custom = await self.availability.windows(job_post_id)
        return custom if custom else await self.availability.windows(None)

    async def open_slots_for_application(
        self, application_id: uuid.UUID
    ) -> list[OpenSlotOut]:
        application = await self.availability.get_application(application_id)
        if application is None:
            raise InterviewApplicationNotFoundError(
                f"Application '{application_id}' not found"
            )
        if application.status != ApplicationStatus.INTERVIEW.value:
            raise ApplicationNotInInterviewError(
                "Interview scheduling is only available while the application "
                f"is in the interview stage (currently '{application.status}')"
            )

        request = await self.availability.get_request_for_application(application_id)
        duration = request.duration_minutes if request else None

        config = await self.availability.get_or_create_config()
        step = duration or config.slot_minutes
        try:
            tz = ZoneInfo(config.timezone)
        except ZoneInfoNotFoundError, ValueError:
            tz = UTC

        rules = await self._resolved_windows(application.job_post_id)
        overrides = await self.availability.overrides(None)
        if not rules and not overrides:
            return []
        by_weekday: dict[int, list[entities.AvailabilityWindow]] = {}
        for rule in rules:
            by_weekday.setdefault(rule.weekday, []).append(rule)

        def windows_for(day: date) -> list[tuple[int, int]]:
            """(start_minute, end_minute) pairs bookable on this calendar date,
            after applying any date override."""
            matched = [o for o in overrides if o.start_date <= day <= o.end_date]
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
        booked = await self.availability.booked_intervals(
            request.id if request else None
        )

        def overlaps_booked(start: datetime) -> bool:
            end = start + timedelta(minutes=step)
            return any(
                start < b_start + timedelta(minutes=b_minutes) and end > b_start
                for b_start, b_minutes in booked
            )

        today_local = now.astimezone(tz).date()
        # Overlapping windows / duplicate overrides can generate the same start
        # instant more than once — key by start so each bookable time appears
        # exactly once.
        by_start: dict[datetime, OpenSlotOut] = {}
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
                    by_start.setdefault(
                        start_utc,
                        OpenSlotOut(
                            starts_at=start_utc,
                            ends_at=start_utc + timedelta(minutes=step),
                        ),
                    )
        return sorted(by_start.values(), key=lambda s: s.starts_at)
