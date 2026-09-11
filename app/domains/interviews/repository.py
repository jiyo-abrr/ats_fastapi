"""Persistence for the per-application interview offer/slot flow (review F07)
— `InterviewRequest` + `InterviewSlot`, used by `scheduling_service.py`.

Stages changes only; callers commit via `UnitOfWork`. The joined reporting
queries (`confirmed_interviews`, `statuses_for_job_post`,
`applications_awaiting_slot_pick`) read `applications`/`users`/`job_posts`
directly — the same sanctioned cross-domain *projection* reads this domain
already documents in CLAUDE.md (interviews → applications/job_posts/auth,
one-way), not something F07 asks to change.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import Row, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.applications.models import Application
from app.domains.auth.models import User
from app.domains.company_addresses.models import CompanyAddress
from app.domains.interviews import entities
from app.domains.interviews.enums import INTERVIEW_RELEASED_APPLICATION_STATUSES
from app.domains.interviews.models import InterviewRequest as InterviewRequestModel
from app.domains.interviews.models import InterviewSlot as InterviewSlotModel
from app.domains.job_posts.models import JobPost


class InterviewRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # -- mapping ---------------------------------------------------------

    @staticmethod
    def _slot_to_entity(obj: InterviewSlotModel) -> entities.InterviewSlot:
        return entities.InterviewSlot(
            id=obj.id,
            request_id=obj.request_id,
            starts_at=obj.starts_at,
            ends_at=obj.ends_at,
            selected_at=obj.selected_at,
            created_at=obj.created_at,
        )

    @staticmethod
    def _request_to_entity(
        obj: InterviewRequestModel, slots: Sequence[InterviewSlotModel]
    ) -> entities.InterviewRequest:
        return entities.InterviewRequest(
            id=obj.id,
            application_id=obj.application_id,
            created_by_user_id=obj.created_by_user_id,
            mode=obj.mode,
            location_or_link=obj.location_or_link,
            company_address_id=obj.company_address_id,
            duration_minutes=obj.duration_minutes,
            notes=obj.notes,
            self_scheduled=obj.self_scheduled,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
            slots=[InterviewRepository._slot_to_entity(s) for s in slots],
        )

    # -- application / company address (read-only, cross-domain — see module
    # docstring) --------------------------------------------------------

    async def get_application(self, application_id: uuid.UUID) -> Application | None:
        return await self.db.get(Application, application_id)

    async def get_company_address(
        self, address_id: uuid.UUID
    ) -> CompanyAddress | None:
        return await self.db.get(CompanyAddress, address_id)

    # -- request + slots ---------------------------------------------------

    async def get_request_with_slots(
        self, application_id: uuid.UUID
    ) -> entities.InterviewRequest | None:
        request = (
            await self.db.execute(
                select(InterviewRequestModel).where(
                    InterviewRequestModel.application_id == application_id
                )
            )
        ).scalar_one_or_none()
        if request is None:
            return None
        slots = (
            (
                await self.db.execute(
                    select(InterviewSlotModel)
                    .where(InterviewSlotModel.request_id == request.id)
                    .order_by(InterviewSlotModel.starts_at)
                )
            )
            .scalars()
            .all()
        )
        return self._request_to_entity(request, slots)

    async def create_request(self, entity: entities.InterviewRequest) -> None:
        self.db.add(
            InterviewRequestModel(
                id=entity.id,
                application_id=entity.application_id,
                created_by_user_id=entity.created_by_user_id,
                mode=entity.mode,
                location_or_link=entity.location_or_link,
                company_address_id=entity.company_address_id,
                duration_minutes=entity.duration_minutes,
                notes=entity.notes,
                self_scheduled=entity.self_scheduled,
            )
        )
        # No relationship() from slots -> request, so the session's automatic
        # insert-ordering can't infer the request must exist first (same
        # reason JobPostService.create() flushes before staging tags).
        await self.db.flush()

    async def update_request_fields(
        self,
        request_id: uuid.UUID,
        *,
        mode: str,
        location_or_link: str | None,
        company_address_id: uuid.UUID | None,
        duration_minutes: int,
        notes: str | None,
        self_scheduled: bool,
    ) -> None:
        obj = await self.db.get(InterviewRequestModel, request_id)
        if obj is None:
            return
        obj.mode = mode
        obj.location_or_link = location_or_link
        obj.company_address_id = company_address_id
        obj.duration_minutes = duration_minutes
        obj.notes = notes
        obj.self_scheduled = self_scheduled

    async def add_slot(self, entity: entities.InterviewSlot) -> None:
        self.db.add(
            InterviewSlotModel(
                id=entity.id,
                request_id=entity.request_id,
                starts_at=entity.starts_at,
                ends_at=entity.ends_at,
            )
        )
        # Flushed immediately so a same-transaction re-fetch by id (see
        # sync_slot_selections) reliably finds it, mirroring the original
        # code's use of the same live Python object across both writes.
        await self.db.flush()

    async def delete_slot(self, slot_id: uuid.UUID) -> None:
        obj = await self.db.get(InterviewSlotModel, slot_id)
        if obj is not None:
            await self.db.delete(obj)

    async def update_slot_ends_at(self, slot_id: uuid.UUID, ends_at: datetime) -> None:
        obj = await self.db.get(InterviewSlotModel, slot_id)
        if obj is not None:
            obj.ends_at = ends_at

    async def sync_slot_selections(self, slots: list[entities.InterviewSlot]) -> None:
        """Writes `selected_at` for every given slot (the confirmed one gets
        `now`, every other live slot on the request gets `None`).

        Clears the old selection and flushes it BEFORE setting the new one.
        `ux_interview_slots_one_selected` is a partial unique *index*, not a
        deferrable constraint, so Postgres checks it per-statement — if the
        ORM's flush happens to emit the "set new slot to now" UPDATE before
        the "clear old slot" one (SQLAlchemy does not preserve Python
        assignment order across a flush), two rows briefly show as selected
        for the same request and the commit fails with "just taken" even
        though nothing was actually taken (review: candidate re-picking a
        time hit this every time, not just on a real race)."""
        to_clear = [s for s in slots if s.selected_at is None]
        to_set = [s for s in slots if s.selected_at is not None]
        for slot in to_clear:
            obj = await self.db.get(InterviewSlotModel, slot.id)
            if obj is not None:
                obj.selected_at = None
        if to_clear:
            await self.db.flush()
        for slot in to_set:
            obj = await self.db.get(InterviewSlotModel, slot.id)
            if obj is not None:
                obj.selected_at = slot.selected_at

    async def overlaps_confirmed(
        self,
        request_id: uuid.UUID,
        starts_at: datetime,
        duration_minutes: int,
    ) -> bool:
        """Any other confirmed interview whose [start, end) overlaps this one."""
        end = starts_at + timedelta(minutes=duration_minutes)
        rows = (
            await self.db.execute(
                select(
                    InterviewSlotModel.starts_at, InterviewRequestModel.duration_minutes
                )
                .join(
                    InterviewRequestModel,
                    InterviewRequestModel.id == InterviewSlotModel.request_id,
                )
                .join(
                    Application,
                    Application.id == InterviewRequestModel.application_id,
                )
                .where(
                    InterviewSlotModel.selected_at.is_not(None),
                    InterviewSlotModel.request_id != request_id,
                    Application.status.not_in(INTERVIEW_RELEASED_APPLICATION_STATUSES),
                )
            )
        ).all()
        return any(
            starts_at < other_start + timedelta(minutes=other_minutes)
            and end > other_start
            for other_start, other_minutes in rows
        )

    async def applications_awaiting_slot_pick(
        self, application_ids: list[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not application_ids:
            return set()
        confirmed_request_ids = (
            select(InterviewSlotModel.request_id)
            .where(InterviewSlotModel.selected_at.is_not(None))
            .scalar_subquery()
        )
        rows = (
            await self.db.execute(
                select(InterviewRequestModel.application_id).where(
                    InterviewRequestModel.application_id.in_(application_ids),
                    InterviewRequestModel.id.not_in(confirmed_request_ids),
                )
            )
        ).all()
        return {row[0] for row in rows}

    async def delete_request(self, application_id: uuid.UUID) -> None:
        await self.db.execute(
            delete(InterviewRequestModel).where(
                InterviewRequestModel.application_id == application_id
            )
        )

    async def statuses_for_job_post(self, job_post_id: uuid.UUID) -> Sequence[Row]:
        return (
            await self.db.execute(
                select(
                    InterviewRequestModel.application_id,
                    InterviewSlotModel.starts_at,
                    InterviewSlotModel.selected_at,
                )
                .join(
                    Application,
                    Application.id == InterviewRequestModel.application_id,
                )
                .outerjoin(
                    InterviewSlotModel,
                    InterviewSlotModel.request_id == InterviewRequestModel.id,
                )
                .where(
                    Application.job_post_id == job_post_id,
                    Application.status.not_in(INTERVIEW_RELEASED_APPLICATION_STATUSES),
                )
            )
        ).all()

    @staticmethod
    def _confirmed_interviews_query():
        return (
            select(
                InterviewRequestModel.application_id,
                InterviewRequestModel.mode,
                InterviewRequestModel.location_or_link,
                InterviewRequestModel.duration_minutes,
                InterviewSlotModel.starts_at,
                User.first_name,
                User.last_name,
                JobPost.job_title,
            )
            .join(
                InterviewRequestModel,
                InterviewRequestModel.id == InterviewSlotModel.request_id,
            )
            .join(
                Application,
                Application.id == InterviewRequestModel.application_id,
            )
            .join(User, User.id == Application.applicant_id)
            .join(JobPost, JobPost.id == Application.job_post_id)
            .where(
                InterviewSlotModel.selected_at.is_not(None),
                Application.status.not_in(INTERVIEW_RELEASED_APPLICATION_STATUSES),
            )
            .order_by(InterviewSlotModel.starts_at)
        )

    async def upcoming_confirmed(self, *, after: datetime, limit: int) -> Sequence[Row]:
        return (
            await self.db.execute(
                self._confirmed_interviews_query()
                .where(InterviewSlotModel.starts_at >= after)
                .limit(limit)
            )
        ).all()

    async def confirmed_within(
        self, *, start: datetime, end: datetime
    ) -> Sequence[Row]:
        return (
            await self.db.execute(
                self._confirmed_interviews_query().where(
                    InterviewSlotModel.starts_at >= start,
                    InterviewSlotModel.starts_at < end,
                )
            )
        ).all()
