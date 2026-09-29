"""FastStream (RabbitMQ) worker for background evaluation-pack exports
(review F09/F26; migrated off arq/Redis — see
docs/plans/rabbitmq-airflow-migration.md).

Run it as its own process, separate from the FastAPI app:

    uv run faststream run app.workers.evaluation_export:app

The sync `GET /applications/export` route (see `evaluations/router.py`) stays
as-is for the common case (<= EVALUATION_PACK_MAX applicants, small résumés);
`POST /applications/export/async` is for job posts too big for that — it
publishes to `EVALUATION_EXPORT_QUEUE` (`app/core/queue.py`) and returns
immediately with a job id to poll.

This module intentionally does NOT go through `ApplicationService.get_resume`'s
owner-or-manage_applications check: the job was already authorized once, at
enqueue time, by the `manage_applications`-gated route. The worker fetches
objects straight from MinIO via `resume_object_key`.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath

from faststream import AckPolicy, FastStream

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.queue import EVALUATION_EXPORT_DLQ, EVALUATION_EXPORT_QUEUE, broker
from app.core.storage import ObjectNotFoundError, get_object, upload_object
from app.core.unit_of_work import UnitOfWork
from app.domains.applications.repository import ApplicationRepository
from app.domains.assessments.attempts.repository import AssessmentAttemptRepository
from app.domains.assessments.attempts.service import AssessmentService
from app.domains.assessments.culture_fit_templates.repository import (
    CultureFitTemplateRepository,
)
from app.domains.assessments.pre_assessment_templates.repository import (
    PreAssessmentTemplateRepository,
)
from app.domains.assessments.technical_assessment_templates.repository import (
    TechnicalAssessmentTemplateRepository,
)
from app.domains.evaluations.export_jobs import EvaluationExportJobRepository
from app.domains.evaluations.export_repository import (
    EvaluationExportRepository,
    ExportApplicant,
)
from app.domains.job_posts.repository import JobPostRepository
from app.use_cases.prepare_evaluation_export import (
    ExportPolicy,
    PrepareEvaluationExport,
)

logger = logging.getLogger(__name__)

# No EVALUATION_PACK_MAX/EVALUATION_PACK_MAX_BYTES cap here — the whole point
# of the async path is to serve the job posts too big for the sync route. A
# much higher ceiling still applies so one export can't run unbounded.
_ASYNC_EXPORT_MAX_APPLICANTS = 5000
_EVALUATION_PACKS_PREFIX = "evaluation_packs/"

app = FastStream(broker)


# One attempt: on an unhandled exception, `AckPolicy.REJECT_ON_ERROR` rejects
# the message without requeuing it, and RabbitMQ routes it straight to
# EVALUATION_EXPORT_DLQ via the queue's x-dead-letter-* arguments (see
# app/core/queue.py) — new visibility arq never gave us (a failed arq job
# just retried silently up to its own default max_tries, then vanished).
# faststream==0.7.5's subscriber has no declarative "retry N times" option
# (that's from an older API generation) — only a binary ack/nack/reject
# policy. If automatic retries are wanted later, they'd need to be
# hand-rolled (e.g. a retry count in a message header, re-published by this
# same handler), not assumed from the decorator.
@broker.subscriber(EVALUATION_EXPORT_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def build_evaluation_export(job_id: str) -> None:
    job_uuid = uuid.UUID(job_id)
    async with AsyncSessionLocal() as db:
        uow = UnitOfWork(db)
        jobs = EvaluationExportJobRepository(db)
        job = await jobs.get_by_id(job_uuid)
        if job is None:
            logger.error("evaluation export job %s not found, skipping", job_id)
            return

        await jobs.mark_running(job_uuid, started_at=datetime.now(UTC))
        await uow.commit()

        try:
            result_key = await _run_export(db, job)
        except Exception as exc:  # noqa: BLE001 — recorded on the job row, re-raised so FastStream retries/DLQs it
            logger.exception("evaluation export job %s failed", job_id)
            await jobs.mark_failed(
                job_uuid, error_message=str(exc), completed_at=datetime.now(UTC)
            )
            await uow.commit()
            raise
        else:
            await jobs.mark_done(
                job_uuid, result_object_key=result_key, completed_at=datetime.now(UTC)
            )
            await uow.commit()


@broker.subscriber(EVALUATION_EXPORT_DLQ)
async def log_dead_lettered_export(job_id: str) -> None:
    """Pure visibility, not a retry path — a job that lands here already has
    `status="failed"` + `error_message` on its `EvaluationExportJob` row
    (set by `build_evaluation_export` on its final attempt, before
    RabbitMQ dead-letters it), so there's nothing left to *do* with the
    message; this just makes sure it also shows up in the worker's own log
    stream, since nothing else watches this queue."""
    logger.error("evaluation export job %s dead-lettered after retries", job_id)


async def _run_export(db, job) -> str:
    job_posts = JobPostRepository(db)
    applications = ApplicationRepository(db)
    attempts = AssessmentAttemptRepository(db)
    assessment_service = AssessmentService(
        attempts,
        PreAssessmentTemplateRepository(db),
        CultureFitTemplateRepository(db),
        TechnicalAssessmentTemplateRepository(db),
        job_posts,
        applications,
        UnitOfWork(db),
    )

    prepare = PrepareEvaluationExport(
        EvaluationExportRepository(db), job_posts, assessment_service
    )

    async def load_resume(row: ExportApplicant) -> tuple[bytes, str] | None:
        if not row.resume_object_key:
            return None
        try:
            data, _content_type = await asyncio.to_thread(
                get_object, settings.minio_bucket, row.resume_object_key
            )
            return data, PurePosixPath(row.resume_object_key).name or "resume"
        except ObjectNotFoundError:
            return None

    result = await prepare.execute(
        job.job_post_id,
        statuses=job.status_filter.split(",") if job.status_filter else None,
        policy=ExportPolicy(_ASYNC_EXPORT_MAX_APPLICANTS),
        load_resume=load_resume,
    )
    object_key = f"{_EVALUATION_PACKS_PREFIX}{job.id}.zip"
    await asyncio.to_thread(
        upload_object,
        settings.minio_bucket,
        object_key,
        result.payload,
        "application/zip",
    )
    return object_key
