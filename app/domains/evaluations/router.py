import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as status_codes
from fastapi.concurrency import run_in_threadpool
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.queue import get_broker
from app.core.storage import ObjectNotFoundError, get_object
from app.domains.applications.dependencies import get_application_service
from app.domains.applications.enums import (
    EVALUATION_ELIGIBLE_STATUSES,
    ApplicationStatus,
)
from app.domains.applications.exceptions import ResumeUnavailableError
from app.domains.applications.service import ApplicationService
from app.domains.auth import entities as auth_entities
from app.domains.auth.dependencies import get_current_user
from app.domains.evaluations.dependencies import (
    get_evaluation_service,
    get_export_job_service,
)
from app.domains.evaluations.exceptions import EvaluationExportJobNotFoundError
from app.domains.evaluations.export_jobs import ExportJobService
from app.domains.evaluations.export_repository import ExportApplicant
from app.domains.evaluations.pack import (
    EVALUATION_PACK_MAX,
    EVALUATION_PACK_MAX_BYTES,
)
from app.domains.evaluations.schemas import (
    ApplicationEvaluationOut,
    EvaluationExportJobOut,
    EvaluationImportIn,
    EvaluationImportResultOut,
    JobEvaluationRowOut,
)
from app.domains.evaluations.service import EvaluationService
from app.domains.job_posts.dependencies import get_job_post_service
from app.domains.job_posts.service import JobPostService
from app.domains.rbac.dependencies import require_permission
from app.use_cases.dependencies import get_prepare_evaluation_export
from app.use_cases.prepare_evaluation_export import (
    ExportLimitExceeded,
    ExportPolicy,
    PrepareEvaluationExport,
)

_manage_applications = Depends(require_permission("manage_applications"))

# Mounted under /applications; every route is manage_applications-gated. These
# are composition roots — they read applications / assessments / job_posts data
# to assemble an evaluation view or pack, without those domains depending back
# on evaluations.
router = APIRouter(
    prefix="/applications",
    tags=["evaluations"],
    dependencies=[_manage_applications],
)


@router.get("/export")
async def export_evaluation_pack(
    job_post_id: uuid.UUID,
    status: list[ApplicationStatus] | None = Query(
        None, description="Restrict the pack to these pipeline statuses"
    ),
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
    prepare: PrepareEvaluationExport = Depends(get_prepare_evaluation_export),
) -> Response:
    async def load_resume(row: ExportApplicant) -> tuple[bytes, str] | None:
        try:
            data, _content_type, filename = await service.get_resume(
                row.id, current_user
            )
            return data, filename
        except ResumeUnavailableError:
            return None

    try:
        result = await prepare.execute(
            job_post_id,
            statuses=[s.value for s in status] if status else None,
            policy=ExportPolicy(EVALUATION_PACK_MAX, EVALUATION_PACK_MAX_BYTES),
            load_resume=load_resume,
        )
    except ExportLimitExceeded as exc:
        raise HTTPException(
            status_code=status_codes.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"{exc} Use POST /applications/export/async instead, "
                "or narrow with ?status=."
            ),
        ) from exc
    slug = re.sub(r"[^a-z0-9]+", "-", result.job_title.lower()).strip("-") or "job"
    return Response(
        content=result.payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}-evaluation-pack.zip"'
        },
    )


@router.post(
    "/export/async",
    response_model=EvaluationExportJobOut,
    status_code=status_codes.HTTP_202_ACCEPTED,
)
async def export_evaluation_pack_async(
    job_post_id: uuid.UUID,
    status: list[ApplicationStatus] | None = Query(
        None, description="Restrict the pack to these pipeline statuses"
    ),
    current_user: auth_entities.User = Depends(get_current_user),
    job_post_service: JobPostService = Depends(get_job_post_service),
    export_jobs: ExportJobService = Depends(get_export_job_service),
    broker: RabbitBroker = Depends(get_broker),
) -> EvaluationExportJobOut:
    """For a job post too big for the synchronous `/export` route: publishes
    the pack build to RabbitMQ (review F09/F26) and returns immediately. Poll
    `GET /applications/export-jobs/{id}` for status, then
    `GET /applications/export-jobs/{id}/download`."""
    await job_post_service.get(job_post_id)  # 404s early if the job post is gone
    job = await export_jobs.enqueue(
        job_post_id=job_post_id,
        requested_by_user_id=current_user.id,
        status_filter=[s.value for s in status] if status else None,
        broker=broker,
    )
    return EvaluationExportJobOut.model_validate(job)


@router.get("/export-jobs/{job_id}", response_model=EvaluationExportJobOut)
async def get_evaluation_export_job(
    job_id: uuid.UUID,
    export_jobs: ExportJobService = Depends(get_export_job_service),
) -> EvaluationExportJobOut:
    job = await export_jobs.get(job_id)
    return EvaluationExportJobOut.model_validate(job)


@router.get("/export-jobs/{job_id}/download")
async def download_evaluation_export(
    job_id: uuid.UUID,
    export_jobs: ExportJobService = Depends(get_export_job_service),
) -> Response:
    job = await export_jobs.get(job_id)
    if job.status != "done" or not job.result_object_key:
        raise HTTPException(
            status_code=status_codes.HTTP_409_CONFLICT,
            detail=f"Export job '{job_id}' is not ready (status: {job.status})",
        )
    try:
        data, _content_type = await run_in_threadpool(
            get_object, settings.minio_bucket, job.result_object_key
        )
    except ObjectNotFoundError as exc:
        raise EvaluationExportJobNotFoundError(
            f"The result for export job '{job_id}' is no longer available"
        ) from exc
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="evaluation-pack-{job_id}.zip"'
            )
        },
    )


@router.get("/evaluations", response_model=Page[JobEvaluationRowOut])
async def job_evaluations(
    job_post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    evaluations: EvaluationService = Depends(get_evaluation_service),
) -> Page[JobEvaluationRowOut]:
    """One row per applicant with their full latest AI evaluation (recommendation,
    fit score, per-dimension scores) — for the Compare tab's side-by-side view.
    Excludes withdrawn/disqualified applicants — they're out of the pipeline,
    so there's no hiring decision left to inform."""
    query = await service.list_for_review(
        job_post_id=job_post_id, statuses=EVALUATION_ELIGIBLE_STATUSES
    )

    async def _transform(rows):
        full = await evaluations.latest_full_for_applications([r.id for r in rows])
        return [
            JobEvaluationRowOut(
                application_id=r.id,
                applicant_first_name=r.applicant_first_name,
                applicant_last_name=r.applicant_last_name,
                applicant_email=r.applicant_email,
                status=r.status,
                hr_assessed=r.hr_assessed,
                evaluation=full.get(r.id),
            )
            for r in rows
        ]

    return await apaginate(db, query, transformer=_transform)


@router.get("/evaluations/export")
async def export_evaluations_csv(
    job_post_id: uuid.UUID,
    evaluations: EvaluationService = Depends(get_evaluation_service),
) -> Response:
    """Flat CSV: latest AI evaluation per applicant, one column per dimension."""
    csv_text = await evaluations.evaluation_csv(job_post_id)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="evaluations.csv"'},
    )


@router.post("/evaluations/import", response_model=EvaluationImportResultOut)
async def import_evaluations(
    payload: EvaluationImportIn,
    current_user: auth_entities.User = Depends(get_current_user),
    evaluations: EvaluationService = Depends(get_evaluation_service),
) -> EvaluationImportResultOut:
    return await evaluations.import_results(
        payload, imported_by_user_id=current_user.id
    )


@router.get(
    "/{application_id}/evaluation",
    response_model=ApplicationEvaluationOut,
)
async def get_application_evaluation(
    application_id: uuid.UUID,
    evaluations: EvaluationService = Depends(get_evaluation_service),
) -> ApplicationEvaluationOut:
    return await evaluations.get_for_application(application_id)
