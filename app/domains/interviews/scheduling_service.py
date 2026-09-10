"""Interview scheduling (Calendly-style, per application).

When an application is in `interview`, HR opens an `InterviewRequest` for it —
the logistics plus a handful of candidate start times (`InterviewSlot`). The
applicant then picks one slot to confirm. Nothing here touches
`ApplicationStatus`; a confirmed slot just hangs off an application that is
already in `interview`.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.models import Application
from app.domains.auth.models import User
from app.domains.interviews.availability_service import InterviewAvailabilityService
from app.domains.interviews.exceptions import (
    ApplicationNotInInterviewError,
    InterviewApplicationNotFoundError,
    InterviewRequestNotFoundError,
    SlotNotOnRequestError,
    SlotUnavailableError,
)
from app.domains.interviews.models import (
    InterviewRequest,
    InterviewSlot,
)
from app.domains.interviews.schemas import (
    InterviewRequestIn,
    InterviewRequestOut,
    InterviewSlotOut,
    InterviewStatusOut,
    SelectSlotIn,
    UpcomingInterviewOut,
)
from app.domains.job_posts.models import JobPost


class InterviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _require_application_in_interview(
        self, application_id: uuid.UUID
    ) -> Application:
        application = await self.db.get(Application, application_id)
        if application is None:
            raise InterviewApplicationNotFoundError(
                f"Application '{application_id}' not found"
            )
        if application.status != ApplicationStatus.INTERVIEW.value:
            raise ApplicationNotInInterviewError(
                "Interview scheduling is only available while the application "
                f"is in the interview stage (currently '{application.status}')"
            )
        return application

    async def _load(
        self, application_id: uuid.UUID
    ) -> tuple[InterviewRequest, list[InterviewSlot]] | None:
        request = (
            await self.db.execute(
                select(InterviewRequest).where(
                    InterviewRequest.application_id == application_id
                )
            )
        ).scalar_one_or_none()
        if request is None:
            return None
        slots = list(
            (
                await self.db.execute(
                    select(InterviewSlot)
                    .where(InterviewSlot.request_id == request.id)
                    .order_by(InterviewSlot.starts_at)
                )
            )
            .scalars()
            .all()
        )
        return request, slots

    def _to_out(
        self, request: InterviewRequest, slots: list[InterviewSlot]
    ) -> InterviewRequestOut:
        selected = next((s for s in slots if s.selected_at is not None), None)
        return InterviewRequestOut(
            id=request.id,
            application_id=request.application_id,
            mode=request.mode,
            location_or_link=request.location_or_link,
            duration_minutes=request.duration_minutes,
            notes=request.notes,
            self_scheduled=request.self_scheduled,
            created_at=request.created_at,
            selected_slot_id=selected.id if selected else None,
            selected_at=selected.selected_at if selected else None,
            slots=[
                InterviewSlotOut(
                    id=s.id,
                    starts_at=s.starts_at,
                    ends_at=s.starts_at + timedelta(minutes=request.duration_minutes),
                    selected=s.selected_at is not None,
                )
                for s in slots
            ],
        )

    async def get_for_application(
        self, application_id: uuid.UUID
    ) -> InterviewRequestOut | None:
        loaded = await self._load(application_id)
        if loaded is None:
            return None
        return self._to_out(*loaded)

    async def set_request(
        self,
        application_id: uuid.UUID,
        payload: InterviewRequestIn,
        *,
        created_by_user_id: uuid.UUID,
    ) -> InterviewRequestOut:
        await self._require_application_in_interview(application_id)
        loaded = await self._load(application_id)

        self_scheduled = not payload.slots

        if loaded is None:
            request = InterviewRequest(
                id=uuid.uuid4(),
                application_id=application_id,
                created_by_user_id=created_by_user_id,
                mode=payload.mode,
                location_or_link=payload.location_or_link,
                duration_minutes=payload.duration_minutes,
                notes=payload.notes,
                self_scheduled=self_scheduled,
            )
            self.db.add(request)
            await self.db.flush()
            existing_slots: list[InterviewSlot] = []
        else:
            request, existing_slots = loaded
            request.mode = payload.mode
            request.location_or_link = payload.location_or_link
            request.duration_minutes = payload.duration_minutes
            request.notes = payload.notes
            request.self_scheduled = self_scheduled

        # Reconcile slots by start time so editing the logistics (or adding a
        # time) keeps any selection the applicant already made. In self-schedule
        # mode `wanted` is empty, so only a slot the candidate already booked
        # survives.
        wanted = {s.starts_at for s in payload.slots}
        current = {s.starts_at: s for s in existing_slots}

        for starts_at, slot in current.items():
            if starts_at not in wanted and slot.selected_at is None:
                await self.db.delete(slot)
        for starts_at in wanted - set(current):
            self.db.add(
                InterviewSlot(
                    id=uuid.uuid4(),
                    request_id=request.id,
                    starts_at=starts_at,
                )
            )

        await self.db.commit()
        return await self.get_for_application(application_id)  # type: ignore[return-value]

    async def _overlaps_confirmed(
        self,
        request_id: uuid.UUID,
        starts_at: datetime,
        duration_minutes: int,
    ) -> bool:
        """Any other confirmed interview whose [start, end) overlaps this one."""
        end = starts_at + timedelta(minutes=duration_minutes)
        rows = (
            await self.db.execute(
                select(InterviewSlot.starts_at, InterviewRequest.duration_minutes)
                .join(
                    InterviewRequest,
                    InterviewRequest.id == InterviewSlot.request_id,
                )
                .where(
                    InterviewSlot.selected_at.is_not(None),
                    InterviewSlot.request_id != request_id,
                )
            )
        ).all()
        return any(
            starts_at < other_start + timedelta(minutes=other_minutes)
            and end > other_start
            for other_start, other_minutes in rows
        )

    async def select_slot(
        self,
        application_id: uuid.UUID,
        payload: SelectSlotIn,
        *,
        selected_by_user_id: uuid.UUID,
    ) -> InterviewRequestOut:
        await self._require_application_in_interview(application_id)
        loaded = await self._load(application_id)
        if loaded is None:
            raise InterviewRequestNotFoundError(
                "No interview has been scheduled for this application yet"
            )
        request, slots = loaded
        now = datetime.now(UTC)

        if payload.slot_id is not None:
            target = next((s for s in slots if s.id == payload.slot_id), None)
            if target is None:
                raise SlotNotOnRequestError(
                    "That time slot is not part of this interview"
                )
            if await self._overlaps_confirmed(
                request.id, target.starts_at, request.duration_minutes
            ):
                raise SlotUnavailableError(
                    "That time overlaps another confirmed interview — pick another."
                )
        else:
            # An open availability instant — must still be open right now.
            open_slots = await InterviewAvailabilityService(
                self.db
            ).open_slots_for_application(application_id)
            if not any(s.starts_at == payload.starts_at for s in open_slots):
                raise SlotUnavailableError(
                    "That time is no longer available — pick another."
                )
            target = next((s for s in slots if s.starts_at == payload.starts_at), None)
            if target is None:
                target = InterviewSlot(
                    id=uuid.uuid4(),
                    request_id=request.id,
                    starts_at=payload.starts_at,
                )
                self.db.add(target)
                slots.append(target)

        # Final overlap guard (covers a booking that landed between the
        # open-slots check and here); the exact-instant unique index is the
        # last line of defence at commit.
        if target.selected_at is None and await self._overlaps_confirmed(
            request.id, target.starts_at, request.duration_minutes
        ):
            raise SlotUnavailableError("That time was just taken — pick another.")

        for slot in slots:
            slot.selected_at = now if slot is target else None
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise SlotUnavailableError(
                "That time was just taken — pick another."
            ) from exc
        return await self.get_for_application(application_id)  # type: ignore[return-value]

    async def pending_selection_application_ids(
        self, application_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Of the given applications, those that have an interview request with
        no slot selected yet — for the "pick a time" nudge on the applicant's
        list."""
        if not application_ids:
            return set()
        rows = (
            await self.db.execute(
                select(InterviewRequest.application_id, InterviewSlot.selected_at)
                .join(
                    InterviewSlot,
                    InterviewSlot.request_id == InterviewRequest.id,
                )
                .where(InterviewRequest.application_id.in_(application_ids))
            )
        ).all()
        has_request: set[uuid.UUID] = set()
        has_selection: set[uuid.UUID] = set()
        for application_id, selected_at in rows:
            has_request.add(application_id)
            if selected_at is not None:
                has_selection.add(application_id)
        return has_request - has_selection

    async def delete_request(self, application_id: uuid.UUID) -> None:
        await self.db.execute(
            delete(InterviewRequest).where(
                InterviewRequest.application_id == application_id
            )
        )
        await self.db.commit()

    async def statuses_for_job_post(
        self, job_post_id: uuid.UUID
    ) -> list[InterviewStatusOut]:
        """`awaiting` / `confirmed` per application that has an interview
        request, for one job post — drives the pipeline view's Interview
        column."""
        rows = (
            await self.db.execute(
                select(
                    InterviewRequest.application_id,
                    InterviewSlot.starts_at,
                    InterviewSlot.selected_at,
                )
                .join(
                    Application,
                    Application.id == InterviewRequest.application_id,
                )
                .outerjoin(
                    InterviewSlot,
                    InterviewSlot.request_id == InterviewRequest.id,
                )
                .where(Application.job_post_id == job_post_id)
            )
        ).all()
        by_app: dict[uuid.UUID, InterviewStatusOut] = {}
        for application_id, starts_at, selected_at in rows:
            entry = by_app.setdefault(
                application_id,
                InterviewStatusOut(application_id=application_id, state="awaiting"),
            )
            if selected_at is not None:
                entry.state = "confirmed"
                entry.starts_at = starts_at
        return list(by_app.values())

    @staticmethod
    def _confirmed_interviews_query():
        return (
            select(
                InterviewRequest.application_id,
                InterviewRequest.mode,
                InterviewRequest.location_or_link,
                InterviewRequest.duration_minutes,
                InterviewSlot.starts_at,
                User.first_name,
                User.last_name,
                JobPost.job_title,
            )
            .join(
                InterviewRequest,
                InterviewRequest.id == InterviewSlot.request_id,
            )
            .join(
                Application,
                Application.id == InterviewRequest.application_id,
            )
            .join(User, User.id == Application.applicant_id)
            .join(JobPost, JobPost.id == Application.job_post_id)
            .where(InterviewSlot.selected_at.is_not(None))
            .order_by(InterviewSlot.starts_at)
        )

    @staticmethod
    def _to_scheduled(r) -> UpcomingInterviewOut:
        return UpcomingInterviewOut(
            application_id=r[0],
            applicant_name=f"{r[5]} {r[6]}",
            job_title=r[7],
            mode=r[1],
            location_or_link=r[2],
            starts_at=r[4],
            ends_at=r[4] + timedelta(minutes=r[3]),
        )

    async def upcoming(self, *, limit: int = 50) -> list[UpcomingInterviewOut]:
        """Confirmed interviews from now onward, soonest first."""
        rows = (
            await self.db.execute(
                self._confirmed_interviews_query()
                .where(InterviewSlot.starts_at >= datetime.now(UTC))
                .limit(limit)
            )
        ).all()
        return [self._to_scheduled(r) for r in rows]

    async def schedule(
        self, *, start: datetime, end: datetime
    ) -> list[UpcomingInterviewOut]:
        """Confirmed interviews starting within `[start, end)` — the schedule
        calendar's month / week / day windows."""
        rows = (
            await self.db.execute(
                self._confirmed_interviews_query().where(
                    InterviewSlot.starts_at >= start,
                    InterviewSlot.starts_at < end,
                )
            )
        ).all()
        return [self._to_scheduled(r) for r in rows]
