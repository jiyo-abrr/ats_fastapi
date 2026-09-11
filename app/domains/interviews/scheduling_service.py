"""Interview scheduling (Calendly-style, per application).

When an application is in `interview`, HR opens an `InterviewRequest` for it —
the logistics plus a handful of candidate start times (`InterviewSlot`). The
applicant then picks one slot to confirm. Nothing here touches
`ApplicationStatus`; a confirmed slot just hangs off an application that is
already in `interview`.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app.core.unit_of_work import UnitOfWork
from app.domains.applications.enums import ApplicationStatus
from app.domains.interviews import entities
from app.domains.interviews.availability_service import InterviewAvailabilityService
from app.domains.interviews.exceptions import (
    ApplicationNotInInterviewError,
    InterviewApplicationNotFoundError,
    InterviewRequestNotFoundError,
    SlotNotOnRequestError,
    SlotUnavailableError,
    UnknownCompanyAddressError,
)
from app.domains.interviews.repository import InterviewRepository
from app.domains.interviews.schemas import (
    InterviewRequestIn,
    InterviewRequestOut,
    InterviewSlotOut,
    InterviewStatusOut,
    ResolvedAddressOut,
    SelectSlotIn,
    UpcomingInterviewOut,
)


class InterviewService:
    def __init__(
        self,
        interviews: InterviewRepository,
        availability: InterviewAvailabilityService,
        uow: UnitOfWork,
    ):
        self.interviews = interviews
        self.availability = availability
        self.uow = uow

    async def _require_application_in_interview(self, application_id: uuid.UUID):
        application = await self.interviews.get_application(application_id)
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

    async def _to_out(self, request: entities.InterviewRequest) -> InterviewRequestOut:
        slots = request.slots or []
        selected = next((s for s in slots if s.selected_at is not None), None)
        # Resolved at read time (see availability_service._presets_out for the
        # same reasoning) so an edited CompanyAddress shows up immediately.
        address = (
            await self.interviews.get_company_address(request.company_address_id)
            if request.company_address_id
            else None
        )
        return InterviewRequestOut(
            id=request.id,
            application_id=request.application_id,
            mode=request.mode,
            location_or_link=request.location_or_link,
            company_address_id=request.company_address_id,
            address=ResolvedAddressOut.model_validate(address) if address else None,
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
        request = await self.interviews.get_request_with_slots(application_id)
        if request is None:
            return None
        return await self._to_out(request)

    async def ensure_default_request(
        self, application_id: uuid.UUID, *, created_by_user_id: uuid.UUID
    ) -> InterviewRequestOut:
        """Auto-provision a self-scheduled interview the instant an
        application enters the interview stage, so the candidate has times to
        pick from immediately — no separate "open the interview" step. A
        no-op if a request already exists (HR may have set one up, with
        hand-picked times, before moving the status). HR can still edit the
        mode/link/duration afterward; that never resets the candidate's pick."""
        existing = await self.get_for_application(application_id)
        if existing is not None:
            return existing
        config = await self.availability.get_global()
        return await self.set_request(
            application_id,
            InterviewRequestIn(
                mode="video",
                location_or_link=None,
                company_address_id=None,
                duration_minutes=config.config.slot_minutes,
                notes=None,
                slots=[],
            ),
            created_by_user_id=created_by_user_id,
        )

    async def set_request(
        self,
        application_id: uuid.UUID,
        payload: InterviewRequestIn,
        *,
        created_by_user_id: uuid.UUID,
    ) -> InterviewRequestOut:
        await self._require_application_in_interview(application_id)
        if payload.company_address_id is not None:
            if await self.interviews.get_company_address(
                payload.company_address_id
            ) is None:
                raise UnknownCompanyAddressError(
                    f"Company address '{payload.company_address_id}' does not exist"
                )
        loaded = await self.interviews.get_request_with_slots(application_id)

        self_scheduled = not payload.slots

        if loaded is None:
            request_id = uuid.uuid4()
            await self.interviews.create_request(
                entities.InterviewRequest(
                    id=request_id,
                    application_id=application_id,
                    created_by_user_id=created_by_user_id,
                    mode=payload.mode,
                    location_or_link=payload.location_or_link,
                    company_address_id=payload.company_address_id,
                    duration_minutes=payload.duration_minutes,
                    notes=payload.notes,
                    self_scheduled=self_scheduled,
                )
            )
            existing_slots: list[entities.InterviewSlot] = []
            duration_minutes = payload.duration_minutes
        else:
            request_id = loaded.id
            existing_slots = loaded.slots or []
            duration_minutes = payload.duration_minutes
            await self.interviews.update_request_fields(
                request_id,
                mode=payload.mode,
                location_or_link=payload.location_or_link,
                company_address_id=payload.company_address_id,
                duration_minutes=payload.duration_minutes,
                notes=payload.notes,
                self_scheduled=self_scheduled,
            )

        # Reconcile slots by start time so editing the logistics (or adding a
        # time) keeps any selection the applicant already made. In self-schedule
        # mode `wanted` is empty, so only a slot the candidate already booked
        # survives.
        wanted = {s.starts_at for s in payload.slots}
        current = {s.starts_at: s for s in existing_slots}

        for starts_at, slot in current.items():
            if starts_at not in wanted and slot.selected_at is None:
                await self.interviews.delete_slot(slot.id)
            elif starts_at in wanted:
                # Keep ends_at in sync with duration_minutes even when the
                # start time itself doesn't change — otherwise editing the
                # duration on an existing offer would silently desync the
                # DB-enforced non-overlap range (review F03).
                await self.interviews.update_slot_ends_at(
                    slot.id, starts_at + timedelta(minutes=duration_minutes)
                )
        for starts_at in wanted - set(current):
            await self.interviews.add_slot(
                entities.InterviewSlot(
                    id=uuid.uuid4(),
                    request_id=request_id,
                    starts_at=starts_at,
                    ends_at=starts_at + timedelta(minutes=duration_minutes),
                )
            )

        await self.uow.commit()
        return await self.get_for_application(application_id)  # type: ignore[return-value]

    async def select_slot(
        self,
        application_id: uuid.UUID,
        payload: SelectSlotIn,
        *,
        selected_by_user_id: uuid.UUID,
    ) -> InterviewRequestOut:
        await self._require_application_in_interview(application_id)
        request = await self.interviews.get_request_with_slots(application_id)
        if request is None:
            raise InterviewRequestNotFoundError(
                "No interview has been scheduled for this application yet"
            )
        slots = request.slots or []
        now = datetime.now(UTC)

        # Idempotent re-confirmation: selecting the slot that is already the
        # confirmed one is a no-op, even if that time is now in the past — the
        # interview is booked, re-clicking must not fail or move it.
        already = next((s for s in slots if s.selected_at is not None), None)
        if already is not None and (
            already.id == payload.slot_id
            or (
                payload.starts_at is not None and already.starts_at == payload.starts_at
            )
        ):
            return await self._to_out(request)

        if payload.slot_id is not None:
            target = next((s for s in slots if s.id == payload.slot_id), None)
            if target is None:
                raise SlotNotOnRequestError(
                    "That time slot is not part of this interview"
                )
            if target.starts_at <= now:
                raise SlotUnavailableError("That time is in the past — pick another.")
            if await self.interviews.overlaps_confirmed(
                request.id, target.starts_at, request.duration_minutes
            ):
                raise SlotUnavailableError(
                    "That time overlaps another confirmed interview — pick another."
                )
        else:
            # An open availability instant. Only allowed when HR did NOT
            # hand-pick specific slots — a manual offer is restrictive.
            if not request.self_scheduled:
                raise SlotNotOnRequestError(
                    "This interview offers specific times — choose one of them "
                    "(slot_id), not an arbitrary time."
                )
            # ...and it must still be open right now.
            open_slots = await self.availability.open_slots_for_application(
                application_id
            )
            if not any(s.starts_at == payload.starts_at for s in open_slots):
                raise SlotUnavailableError(
                    "That time is no longer available — pick another."
                )
            target = next((s for s in slots if s.starts_at == payload.starts_at), None)
            if target is None:
                target = entities.InterviewSlot(
                    id=uuid.uuid4(),
                    request_id=request.id,
                    starts_at=payload.starts_at,
                    ends_at=payload.starts_at
                    + timedelta(minutes=request.duration_minutes),
                )
                await self.interviews.add_slot(target)
                slots.append(target)

        # Final overlap guard (covers a booking that landed between the
        # open-slots check and here); the exact-instant unique index is the
        # last line of defence at commit.
        if target.selected_at is None and await self.interviews.overlaps_confirmed(
            request.id, target.starts_at, request.duration_minutes
        ):
            raise SlotUnavailableError("That time was just taken — pick another.")

        for slot in slots:
            slot.selected_at = now if slot is target else None
        await self.interviews.sync_slot_selections(slots)
        try:
            await self.uow.commit()
        except IntegrityError as exc:
            await self.uow.rollback()
            raise SlotUnavailableError(
                "That time was just taken — pick another."
            ) from exc
        return await self.get_for_application(application_id)  # type: ignore[return-value]

    async def applications_awaiting_slot_pick(
        self, application_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Of the given applications, those with an interview request whose time
        is not confirmed yet — for the "pick a time" nudge on the applicant's
        list. A self-scheduled request has zero slot rows until the candidate
        books one, so this must NOT inner-join to slots (that would silently
        drop exactly the requests that most need the nudge)."""
        return await self.interviews.applications_awaiting_slot_pick(application_ids)

    async def delete_request(self, application_id: uuid.UUID) -> None:
        await self.interviews.delete_request(application_id)
        await self.uow.commit()

    async def statuses_for_job_post(
        self, job_post_id: uuid.UUID
    ) -> list[InterviewStatusOut]:
        """`awaiting` / `confirmed` per application that has an interview
        request, for one job post — drives the pipeline view's Interview
        column."""
        rows = await self.interviews.statuses_for_job_post(job_post_id)
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
        rows = await self.interviews.upcoming_confirmed(
            after=datetime.now(UTC), limit=limit
        )
        return [self._to_scheduled(r) for r in rows]

    async def schedule(
        self, *, start: datetime, end: datetime
    ) -> list[UpcomingInterviewOut]:
        """Confirmed interviews starting within `[start, end)` — the schedule
        calendar's month / week / day windows."""
        rows = await self.interviews.confirmed_within(start=start, end=end)
        return [self._to_scheduled(r) for r in rows]
