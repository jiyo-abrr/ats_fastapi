"""Background evaluation-pack export jobs (review F09/F26).

`EvaluationExportJob` tracks one async pack build end to end: `pending` when
enqueued, `running` while the RabbitMQ/FastStream worker builds it, `done`
(with `result_object_key` in MinIO) or `failed` (with `error_message`) when
finished. This is new code, not a rework of the rest of `evaluations/` (which
still takes `AsyncSession` directly — see docs/architecture.md's F07 note) —
it gets the plain-dataclass-entity + repository treatment because it's small,
self-contained, and has no reason to inherit that domain's session-in-service
style.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from faststream.rabbit import RabbitBroker
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.queue import EVALUATION_EXPORT_QUEUE
from app.core.unit_of_work import UnitOfWork
from app.domains.evaluations.exceptions import EvaluationExportJobNotFoundError
from app.domains.evaluations.models import (
    EvaluationExportJob as EvaluationExportJobModel,
)


@dataclass
class EvaluationExportJob:
    id: uuid.UUID
    job_post_id: uuid.UUID
    requested_by_user_id: uuid.UUID
    status: str = "pending"
    status_filter: str | None = None
    result_object_key: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class EvaluationExportJobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _to_entity(obj: EvaluationExportJobModel) -> EvaluationExportJob:
        return EvaluationExportJob(
            id=obj.id,
            job_post_id=obj.job_post_id,
            requested_by_user_id=obj.requested_by_user_id,
            status=obj.status,
            status_filter=obj.status_filter,
            result_object_key=obj.result_object_key,
            error_message=obj.error_message,
            created_at=obj.created_at,
            started_at=obj.started_at,
            completed_at=obj.completed_at,
        )

    async def create(self, entity: EvaluationExportJob) -> None:
        self.db.add(
            EvaluationExportJobModel(
                id=entity.id,
                job_post_id=entity.job_post_id,
                requested_by_user_id=entity.requested_by_user_id,
                status=entity.status,
                status_filter=entity.status_filter,
            )
        )

    async def get_by_id(self, job_id: uuid.UUID) -> EvaluationExportJob | None:
        obj = await self.db.get(EvaluationExportJobModel, job_id)
        return self._to_entity(obj) if obj is not None else None

    async def mark_running(self, job_id: uuid.UUID, started_at: datetime) -> None:
        obj = await self.db.get(EvaluationExportJobModel, job_id)
        if obj is None:
            return
        obj.status = "running"
        obj.started_at = started_at

    async def mark_done(
        self, job_id: uuid.UUID, *, result_object_key: str, completed_at: datetime
    ) -> None:
        obj = await self.db.get(EvaluationExportJobModel, job_id)
        if obj is None:
            return
        obj.status = "done"
        obj.result_object_key = result_object_key
        obj.completed_at = completed_at

    async def mark_failed(
        self, job_id: uuid.UUID, *, error_message: str, completed_at: datetime
    ) -> None:
        obj = await self.db.get(EvaluationExportJobModel, job_id)
        if obj is None:
            return
        obj.status = "failed"
        # Trimmed to the column width — this is an operator-facing summary,
        # full detail belongs in the worker's own logs, not the DB row.
        obj.error_message = error_message[:2000]
        obj.completed_at = completed_at

    async def list_for_job_post(
        self, job_post_id: uuid.UUID, *, limit: int = 20
    ) -> list[EvaluationExportJob]:
        result = await self.db.execute(
            select(EvaluationExportJobModel)
            .where(EvaluationExportJobModel.job_post_id == job_post_id)
            .order_by(EvaluationExportJobModel.created_at.desc())
            .limit(limit)
        )
        return [self._to_entity(obj) for obj in result.scalars().all()]


class ExportJobService:
    """Enqueue/poll side of the async export — the actual pack-building logic
    lives in `app/workers/evaluation_export.py` (a FastStream/RabbitMQ
    consumer), never here. Router endpoints are manage_applications-gated,
    so this service does no further authorization of its own."""

    def __init__(self, jobs: EvaluationExportJobRepository, uow: UnitOfWork):
        self.jobs = jobs
        self.uow = uow

    async def enqueue(
        self,
        *,
        job_post_id: uuid.UUID,
        requested_by_user_id: uuid.UUID,
        status_filter: list[str] | None,
        broker: RabbitBroker,
    ) -> EvaluationExportJob:
        job_id = uuid.uuid4()
        entity = EvaluationExportJob(
            id=job_id,
            job_post_id=job_post_id,
            requested_by_user_id=requested_by_user_id,
            status_filter=",".join(status_filter) if status_filter else None,
        )
        await self.jobs.create(entity)
        await self.uow.commit()
        await broker.publish(str(job_id), EVALUATION_EXPORT_QUEUE)
        return entity

    async def get(self, job_id: uuid.UUID) -> EvaluationExportJob:
        job = await self.jobs.get_by_id(job_id)
        if job is None:
            raise EvaluationExportJobNotFoundError(
                f"Evaluation export job '{job_id}' not found"
            )
        return job

    async def list_for_job_post(
        self, job_post_id: uuid.UUID
    ) -> list[EvaluationExportJob]:
        return await self.jobs.list_for_job_post(job_post_id)
