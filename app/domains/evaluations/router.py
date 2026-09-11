import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi import status as status_codes
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.applications.dependencies import get_application_service
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.exceptions import ResumeUnavailableError
from app.domains.applications.service import ApplicationService
from app.domains.assessments.attempts.dependencies import get_assessment_service
from app.domains.assessments.attempts.service import AssessmentService
from app.domains.auth import entities as auth_entities
from app.domains.auth.dependencies import get_current_user
from app.domains.evaluations.dependencies import get_evaluation_service
from app.domains.evaluations.pack import (
    EVALUATION_PACK_MAX,
    EVALUATION_PACK_MAX_BYTES,
    build_evaluation_pack,
)
from app.domains.evaluations.schemas import (
    ApplicationEvaluationOut,
    EvaluationImportIn,
    EvaluationImportResultOut,
    JobEvaluationRowOut,
)
from app.domains.evaluations.service import EvaluationService
from app.domains.job_posts.dependencies import get_job_post_service
from app.domains.job_posts.service import JobPostService
from app.domains.rbac.dependencies import require_permission

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
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    assessment_service: AssessmentService = Depends(get_assessment_service),
    job_post_service: JobPostService = Depends(get_job_post_service),
) -> Response:
    """ZIP for external AI evaluation: job spec + rubric + every applicant's
    résumé and assessment answers. Bounded by applicant count and total bytes —
    narrow with `?status=` when a job post is over the cap."""
    job = await job_post_service.get(job_post_id)
    query = await service.list_for_review(
        job_post_id=job_post_id,
        statuses=[s.value for s in status] if status else None,
    )
    # Fetch one past the cap so an over-limit job post is a cheap 413, not a
    # full table scan.
    rows = (await db.execute(query.limit(EVALUATION_PACK_MAX + 1))).all()

    if len(rows) > EVALUATION_PACK_MAX:
        raise HTTPException(
            status_code=status_codes.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"More than {EVALUATION_PACK_MAX} applicants match. Narrow with "
                "?status=applied (repeatable) or split the export."
            ),
        )

    applicants: list[dict] = []
    total_bytes = 0
    for row in rows:
        try:
            data, _content_type, filename = await service.get_resume(
                row.id, current_user
            )
            total_bytes += len(data)
            if total_bytes > EVALUATION_PACK_MAX_BYTES:
                raise HTTPException(
                    status_code=status_codes.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        "The résumés for this set exceed the "
                        f"{EVALUATION_PACK_MAX_BYTES // (1024 * 1024)} MiB export "
                        "limit. Narrow with ?status=."
                    ),
                )
            resume = (data, filename)
        except ResumeUnavailableError:
            resume = None
        reviews = await assessment_service.list_review_for_application(row.id)
        applicants.append({"row": row, "resume": resume, "reviews": reviews})

    payload = build_evaluation_pack(job=job, applicants=applicants)
    slug = re.sub(r"[^a-z0-9]+", "-", job.job_title.lower()).strip("-") or "job"
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{slug}-evaluation-pack.zip"'
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
    fit score, per-dimension scores) — for the Compare tab's side-by-side view."""
    query = await service.list_for_review(job_post_id=job_post_id, statuses=None)

    async def _transform(rows):
        full = await evaluations.latest_full_for_applications([r.id for r in rows])
        return [
            JobEvaluationRowOut(
                application_id=r.id,
                applicant_first_name=r.applicant_first_name,
                applicant_last_name=r.applicant_last_name,
                applicant_email=r.applicant_email,
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
