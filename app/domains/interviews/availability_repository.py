"""Persistence for interview availability (review F07) — `InterviewConfig`,
`InterviewAvailabilityRule`, `InterviewDateOverride`, `JobPostInterviewer`;
used by `availability_service.py`. A separate module (not `repository.py`,
which is `InterviewRepository` for the request/slot flow) mirroring the two
service objects this domain already documents in CLAUDE.md.

`JobPostInterviewer` (a pure job_post_id/user_id association row, no other
fields) has no entity of its own — a whole-list replace managed directly
here, the same as `job_posts`' own `job_post_tags`/`job_post_exclusions` join
tables.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.applications.models import Application
from app.domains.auth.models import User
from app.domains.interviews import entities
from app.domains.interviews.enums import INTERVIEW_RELEASED_APPLICATION_STATUSES
from app.domains.interviews.models import (
    InterviewAvailabilityRule,
    InterviewDateOverride,
    JobPostInterviewer,
)
from app.domains.interviews.models import InterviewConfig as InterviewConfigModel
from app.domains.interviews.models import InterviewRequest as InterviewRequestModel
from app.domains.interviews.models import InterviewSlot as InterviewSlotModel
from app.domains.job_posts.models import JobPost
from app.domains.rbac.models import Role

_CONFIG_ID = 1


class InterviewAvailabilityRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # -- config ------------------------------------------------------------

    @staticmethod
    def _config_to_entity(obj: InterviewConfigModel) -> entities.InterviewConfig:
        return entities.InterviewConfig(
            id=obj.id,
            slot_minutes=obj.slot_minutes,
            horizon_days=obj.horizon_days,
            min_notice_hours=obj.min_notice_hours,
            timezone=obj.timezone,
            updated_at=obj.updated_at,
        )

    async def get_or_create_config(self) -> entities.InterviewConfig:
        obj = await self.db.get(InterviewConfigModel, _CONFIG_ID)
        if obj is None:
            obj = InterviewConfigModel(id=_CONFIG_ID)
            self.db.add(obj)
            await self.db.flush()
        return self._config_to_entity(obj)

    async def save_config(self, config: entities.InterviewConfig) -> None:
        obj = await self.db.get(InterviewConfigModel, config.id)
        if obj is None:
            return
        obj.slot_minutes = config.slot_minutes
        obj.horizon_days = config.horizon_days
        obj.min_notice_hours = config.min_notice_hours
        obj.timezone = config.timezone

    # -- availability windows ---------------------------------------------

    @staticmethod
    def _window_to_entity(
        obj: InterviewAvailabilityRule,
    ) -> entities.AvailabilityWindow:
        return entities.AvailabilityWindow(
            id=obj.id,
            job_post_id=obj.job_post_id,
            weekday=obj.weekday,
            start_minute=obj.start_minute,
            end_minute=obj.end_minute,
            created_at=obj.created_at,
        )

    async def windows(
        self, job_post_id: uuid.UUID | None
    ) -> list[entities.AvailabilityWindow]:
        stmt = select(InterviewAvailabilityRule).order_by(
            InterviewAvailabilityRule.weekday,
            InterviewAvailabilityRule.start_minute,
        )
        stmt = (
            stmt.where(InterviewAvailabilityRule.job_post_id.is_(None))
            if job_post_id is None
            else stmt.where(InterviewAvailabilityRule.job_post_id == job_post_id)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._window_to_entity(r) for r in rows]

    async def replace_windows(
        self,
        job_post_id: uuid.UUID | None,
        windows: list[entities.AvailabilityWindow],
    ) -> None:
        clause = (
            InterviewAvailabilityRule.job_post_id.is_(None)
            if job_post_id is None
            else InterviewAvailabilityRule.job_post_id == job_post_id
        )
        await self.db.execute(delete(InterviewAvailabilityRule).where(clause))
        for window in windows:
            self.db.add(
                InterviewAvailabilityRule(
                    id=window.id,
                    job_post_id=job_post_id,
                    weekday=window.weekday,
                    start_minute=window.start_minute,
                    end_minute=window.end_minute,
                )
            )

    # -- date overrides ------------------------------------------------

    @staticmethod
    def _override_to_entity(obj: InterviewDateOverride) -> entities.DateOverride:
        return entities.DateOverride(
            id=obj.id,
            job_post_id=obj.job_post_id,
            start_date=obj.start_date,
            end_date=obj.end_date,
            is_unavailable=obj.is_unavailable,
            start_minute=obj.start_minute,
            end_minute=obj.end_minute,
            note=obj.note,
            created_at=obj.created_at,
        )

    async def overrides(
        self, job_post_id: uuid.UUID | None
    ) -> list[entities.DateOverride]:
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
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._override_to_entity(r) for r in rows]

    async def replace_overrides(
        self,
        job_post_id: uuid.UUID | None,
        overrides: list[entities.DateOverride],
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
                    id=ov.id,
                    job_post_id=job_post_id,
                    start_date=ov.start_date,
                    end_date=ov.end_date,
                    is_unavailable=ov.is_unavailable,
                    start_minute=ov.start_minute,
                    end_minute=ov.end_minute,
                    note=ov.note,
                )
            )

    # -- staff / interviewers (cross-domain projections) -----------------

    async def list_staff(self) -> Sequence[User]:
        """Every admin / HR account — the pool for a job post's interviewer
        list."""
        return (
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

    async def get_job_post(self, job_post_id: uuid.UUID) -> JobPost | None:
        return await self.db.get(JobPost, job_post_id)

    async def interviewers(self, job_post_id: uuid.UUID) -> Sequence[User]:
        return (
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

    async def valid_user_ids(self, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        return set(
            (await self.db.execute(select(User.id).where(User.id.in_(user_ids))))
            .scalars()
            .all()
        )

    async def replace_interviewers(
        self, job_post_id: uuid.UUID, user_ids: list[uuid.UUID]
    ) -> None:
        await self.db.execute(
            delete(JobPostInterviewer).where(
                JobPostInterviewer.job_post_id == job_post_id
            )
        )
        for user_id in user_ids:
            self.db.add(
                JobPostInterviewer(
                    id=uuid.uuid4(),
                    job_post_id=job_post_id,
                    user_id=user_id,
                )
            )

    # -- slot generation (cross-domain projections) ----------------------

    async def get_application(self, application_id: uuid.UUID) -> Application | None:
        return await self.db.get(Application, application_id)

    async def get_request_for_application(
        self, application_id: uuid.UUID
    ) -> InterviewRequestModel | None:
        return (
            await self.db.execute(
                select(InterviewRequestModel).where(
                    InterviewRequestModel.application_id == application_id
                )
            )
        ).scalar_one_or_none()

    async def booked_intervals(
        self, exclude_request_id: uuid.UUID | None
    ) -> list[tuple]:
        """`(start, duration_minutes)` for every confirmed interview across the
        org — used to block times that overlap an existing booking, not just
        exact-instant clashes."""
        stmt = (
            select(InterviewSlotModel.starts_at, InterviewRequestModel.duration_minutes)
            .join(
                InterviewRequestModel,
                InterviewRequestModel.id == InterviewSlotModel.request_id,
            )
            .join(Application, Application.id == InterviewRequestModel.application_id)
            .where(
                InterviewSlotModel.selected_at.is_not(None),
                Application.status.not_in(INTERVIEW_RELEASED_APPLICATION_STATUSES),
            )
        )
        if exclude_request_id is not None:
            stmt = stmt.where(InterviewRequestModel.id != exclude_request_id)
        return [(row[0], row[1]) for row in (await self.db.execute(stmt)).all()]
