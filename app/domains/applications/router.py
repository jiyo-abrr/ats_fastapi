import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.http_headers import content_disposition_attachment
from app.domains.applications.dependencies import get_application_service
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.schemas import (
    ApplicantSummaryOut,
    ApplicationAssessmentsOut,
    ApplicationCreate,
    ApplicationOut,
    ApplicationReviewOut,
    ApplicationScorecardOut,
    ApplicationStatsOut,
    ApplicationStatusUpdate,
    ApplicationSummaryOut,
    AssessmentDeadlineExtensionOut,
    AttemptSummaryOut,
    EvaluationSummaryOut,
    ExtendAssessmentDeadlineRequest,
    JobAssessmentReviewRowOut,
)
from app.domains.applications.service import ApplicationService
from app.domains.assessments.attempts.dependencies import get_assessment_service
from app.domains.assessments.attempts.schemas import (
    AssessmentAttemptOut,
    AttemptReviewOut,
)
from app.domains.assessments.attempts.service import AssessmentService
from app.domains.auth import entities as auth_entities
from app.domains.auth.dependencies import get_current_user
from app.domains.evaluations.dependencies import get_evaluation_service
from app.domains.evaluations.service import EvaluationService
from app.domains.interviews.dependencies import get_interview_service
from app.domains.interviews.scheduling_service import InterviewService
from app.domains.rbac.dependencies import require_permission
from app.use_cases.apply_to_job import ApplyToJob
from app.use_cases.dependencies import get_apply_to_job

_manage_applications = Depends(require_permission("manage_applications"))

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: ApplicationCreate,
    current_user: auth_entities.User = Depends(get_current_user),
    apply_to_job: ApplyToJob = Depends(get_apply_to_job),
) -> ApplicationOut:
    # One transaction owner: the use case stages the application AND its
    # assessment attempts, then commits once. See app/use_cases/apply_to_job.py.
    return await apply_to_job.execute(
        job_post_id=payload.job_post_id, current_user=current_user
    )


@router.get("/me", response_model=Page[ApplicationSummaryOut])
async def list_my_applications(
    job_post_id: uuid.UUID | None = None,
    current_user: auth_entities.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    interviews: InterviewService = Depends(get_interview_service),
) -> Page[ApplicationSummaryOut]:
    query = await service.list_for_applicant(current_user.id, job_post_id=job_post_id)

    async def _transform(rows):
        interview_ids = [r.id for r in rows if r.status == ApplicationStatus.INTERVIEW]
        pending = await interviews.applications_awaiting_slot_pick(interview_ids)
        out = []
        for r in rows:
            dto = ApplicationSummaryOut.model_validate(r)
            if r.id in pending:
                dto.pending_applicant_action = "pick_interview_time"
            out.append(dto)
        return out

    return await apaginate(db, query, transformer=_transform)


@router.get(
    "/stats",
    response_model=ApplicationStatsOut,
    dependencies=[_manage_applications],
)
async def application_stats(
    job_post_id: uuid.UUID | None = None,
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationStatsOut:
    return ApplicationStatsOut(**await service.stats(job_post_id))


@router.get(
    "",
    response_model=Page[ApplicationReviewOut],
    dependencies=[_manage_applications],
)
async def list_applications(
    job_post_id: uuid.UUID | None = None,
    status: list[ApplicationStatus] | None = Query(None),
    applicant_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
) -> Page[ApplicationReviewOut]:
    query = await service.list_for_review(
        job_post_id=job_post_id,
        statuses=[s.value for s in status] if status else None,
        applicant_id=applicant_id,
    )
    return await apaginate(
        db,
        query,
        transformer=lambda rows: [ApplicationReviewOut.model_validate(r) for r in rows],
    )


@router.get(
    "/applicants",
    response_model=Page[ApplicantSummaryOut],
    dependencies=[_manage_applications],
)
async def list_applicants(
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
) -> Page[ApplicantSummaryOut]:
    query = await service.list_applicants(search=search)
    return await apaginate(
        db,
        query,
        transformer=lambda rows: [ApplicantSummaryOut.model_validate(r) for r in rows],
    )


@router.get(
    "/assessment-scorecard",
    response_model=Page[ApplicationScorecardOut],
    dependencies=[_manage_applications],
)
async def assessment_scorecard(
    job_post_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    assessment_service: AssessmentService = Depends(get_assessment_service),
    evaluations: EvaluationService = Depends(get_evaluation_service),
) -> Page[ApplicationScorecardOut]:
    query = await service.list_for_review(job_post_id=job_post_id, statuses=None)

    async def _transform(rows):
        ids = [r.id for r in rows]
        summaries = await assessment_service.summaries_for_applications(ids)
        evals = await evaluations.latest_summaries_for_applications(ids)
        return [
            ApplicationScorecardOut(
                id=r.id,
                created_at=r.created_at,
                status=r.status,
                applicant_first_name=r.applicant_first_name,
                applicant_last_name=r.applicant_last_name,
                applicant_email=r.applicant_email,
                assessments=[
                    AttemptSummaryOut(**summary) for summary in summaries.get(r.id, [])
                ],
                evaluation=(
                    EvaluationSummaryOut(**evals[r.id]) if r.id in evals else None
                ),
            )
            for r in rows
        ]

    return await apaginate(db, query, transformer=_transform)


@router.get(
    "/assessment-review",
    response_model=Page[JobAssessmentReviewRowOut],
    dependencies=[_manage_applications],
)
async def job_assessment_review(
    job_post_id: uuid.UUID,
    template_type: str,
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
    assessment_service: AssessmentService = Depends(get_assessment_service),
) -> Page[JobAssessmentReviewRowOut]:
    query = await service.list_for_review(job_post_id=job_post_id, statuses=None)

    async def _transform(rows):
        out: list[JobAssessmentReviewRowOut] = []
        for r in rows:
            reviews = await assessment_service.list_review_for_application(r.id)
            match = next(
                (rv for rv in reviews if rv["template_type"] == template_type),
                None,
            )
            out.append(
                JobAssessmentReviewRowOut(
                    application_id=r.id,
                    applicant_first_name=r.applicant_first_name,
                    applicant_last_name=r.applicant_last_name,
                    applicant_email=r.applicant_email,
                    attempt=AttemptReviewOut.model_validate(match) if match else None,
                )
            )
        return out

    return await apaginate(db, query, transformer=_transform)


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.get(application_id, current_user)


@router.get("/{application_id}/resume")
async def download_resume(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> Response:
    data, content_type, filename = await service.get_resume(
        application_id, current_user
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": content_disposition_attachment(filename)},
    )


@router.post("/{application_id}/withdraw", response_model=ApplicationOut)
async def withdraw_application(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.withdraw(application_id, current_user)


@router.patch(
    "/{application_id}/status",
    response_model=ApplicationOut,
    dependencies=[_manage_applications],
)
async def update_application_status(
    application_id: uuid.UUID,
    payload: ApplicationStatusUpdate,
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.update_status(application_id, payload.status)


@router.patch(
    "/{application_id}/extend-assessment-deadline",
    response_model=ApplicationOut,
    dependencies=[_manage_applications],
)
async def extend_assessment_deadline(
    application_id: uuid.UUID,
    payload: ExtendAssessmentDeadlineRequest,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.extend_assessment_deadline(
        application_id,
        new_deadline=payload.new_deadline,
        extend_by_days=payload.extend_by_days,
        reason=payload.reason,
        current_user=current_user,
    )


@router.get(
    "/{application_id}/assessments/review",
    response_model=list[AttemptReviewOut],
    dependencies=[_manage_applications],
)
async def get_application_assessments_review(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
    assessment_service: AssessmentService = Depends(get_assessment_service),
) -> list[AttemptReviewOut]:
    # Reuses ApplicationService.get() for the existence + access check
    # (the route's _manage_applications dep already gates the permission).
    await service.get(application_id, current_user)
    reviews = await assessment_service.list_review_for_application(application_id)
    return [AttemptReviewOut.model_validate(r) for r in reviews]


@router.get(
    "/{application_id}/assessments",
    response_model=ApplicationAssessmentsOut,
)
async def get_application_assessments(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
    assessment_service: AssessmentService = Depends(get_assessment_service),
) -> ApplicationAssessmentsOut:
    # ApplicationService.get() enforces the owner-or-manage_applications
    # check — the same rule this endpoint needs, so it's reused rather than
    # duplicated here.
    await service.get(application_id, current_user)
    attempts = await assessment_service.list_for_application(application_id)
    extensions = await service.list_deadline_extensions(application_id)
    return ApplicationAssessmentsOut(
        attempts=[AssessmentAttemptOut.model_validate(a) for a in attempts],
        deadline_extensions=[
            AssessmentDeadlineExtensionOut.model_validate(e) for e in extensions
        ],
    )
