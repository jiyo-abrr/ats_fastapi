"""arq worker for background evaluation-pack exports (review F09/F26).

Run it as its own process, separate from the FastAPI app:

    uv run arq app.workers.evaluation_export.WorkerSettings

The sync `GET /applications/export` route (see `evaluations/router.py`) stays
as-is for the common case (<= EVALUATION_PACK_MAX applicants, small résumés);
`POST /applications/export/async` is for job posts too big for that — it
enqueues `build_evaluation_export` here and returns immediately with a job id
to poll.

This module intentionally does NOT go through `AssessmentService.get_resume`'s
owner-or-manage_applications check: the job was already authorized once, at
enqueue time, by the `manage_applications`-gated route. The worker fetches
objects straight from MinIO via `resume_object_key`.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import PurePosixPath

from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.job_queue import redis_settings
from app.core.storage import ObjectNotFoundError, get_object, upload_object
from app.core.unit_of_work import UnitOfWork
from app.domains.applications.models import Application as ApplicationModel
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
from app.domains.evaluations.pack import build_evaluation_pack
from app.domains.job_posts.repository import JobPostRepository

logger = logging.getLogger(__name__)

# No EVALUATION_PACK_MAX/EVALUATION_PACK_MAX_BYTES cap here — the whole point
# of the async path is to serve the job posts too big for the sync route. A
# much higher ceiling still applies so one export can't run unbounded.
_ASYNC_EXPORT_MAX_APPLICANTS = 5000
_EVALUATION_PACKS_PREFIX = "evaluation_packs/"


async def build_evaluation_export(ctx: dict, job_id: str) -> None:
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
        except Exception as exc:  # noqa: BLE001 — recorded on the job row, re-raised for arq's own retry/log
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

    job_post = await job_posts.get_by_id(job.job_post_id)
    if job_post is None:
        raise ValueError(f"job post '{job.job_post_id}' no longer exists")

    statuses = job.status_filter.split(",") if job.status_filter else None
    query = await applications.list_for_review(
        job_post_id=job.job_post_id, statuses=statuses
    )
    rows = (await db.execute(query.limit(_ASYNC_EXPORT_MAX_APPLICANTS))).all()

    resume_keys: dict[uuid.UUID, str | None] = {}
    if rows:
        key_rows = await db.execute(
            select(ApplicationModel.id, ApplicationModel.resume_object_key).where(
                ApplicationModel.id.in_([r.id for r in rows])
            )
        )
        resume_keys = dict(key_rows.all())

    applicants: list[dict] = []
    for row in rows:
        resume = None
        object_key = resume_keys.get(row.id)
        if object_key:
            try:
                data, _content_type = await asyncio.to_thread(
                    get_object, settings.minio_bucket, object_key
                )
                resume = (data, PurePosixPath(object_key).name or "resume")
            except ObjectNotFoundError:
                resume = None
        reviews = await assessment_service.list_review_for_application(row.id)
        applicants.append({"row": row, "resume": resume, "reviews": reviews})

    payload = build_evaluation_pack(job=job_post, applicants=applicants)
    object_key = f"{_EVALUATION_PACKS_PREFIX}{job.id}.zip"
    await asyncio.to_thread(
        upload_object, settings.minio_bucket, object_key, payload, "application/zip"
    )
    return object_key


class WorkerSettings:
    functions = [build_evaluation_export]
    redis_settings: RedisSettings = redis_settings()
