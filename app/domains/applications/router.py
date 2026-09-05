import uuid

from fastapi import APIRouter, Depends, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.applications.dependencies import get_application_service
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.schemas import (
    ApplicationAssessmentsOut,
    ApplicationCreate,
    ApplicationOut,
    ApplicationReviewOut,
    ApplicationStatusUpdate,
    ApplicationSummaryOut,
    AssessmentDeadlineExtensionOut,
    ExtendAssessmentDeadlineRequest,
)
from app.domains.applications.service import ApplicationService
from app.domains.assessments.dependencies import get_assessment_service
from app.domains.assessments.schemas import AssessmentAttemptOut
from app.domains.assessments.service import AssessmentService
from app.domains.auth import entities as auth_entities
from app.domains.auth.dependencies import get_current_user
from app.domains.rbac.dependencies import require_permission

_manage_applications = Depends(require_permission("manage_applications"))

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("", response_model=ApplicationOut, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: ApplicationCreate,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
    assessment_service: AssessmentService = Depends(get_assessment_service),
) -> ApplicationOut:
    application = await service.create(
        job_post_id=payload.job_post_id, current_user=current_user
    )
    # Router-level composition, not a service-to-service dependency: creating
    # an application's assessment attempts touches both applications and
    # assessments, and those two domains can't depend on each other (assessments
    # already depends on applications — see applications-status-pipeline.md's
    # scheduler section for the same cycle problem, resolved the same way).
    await assessment_service.create_attempts_for_application(
        application.id, payload.job_post_id
    )
    return application


@router.get("/me", response_model=Page[ApplicationSummaryOut])
async def list_my_applications(
    current_user: auth_entities.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
) -> Page[ApplicationSummaryOut]:
    query = await service.list_for_applicant(current_user.id)
    return await apaginate(
        db,
        query,
        transformer=lambda rows: [
            ApplicationSummaryOut.model_validate(r) for r in rows
        ],
    )


@router.get(
    "",
    response_model=Page[ApplicationReviewOut],
    dependencies=[_manage_applications],
)
async def list_applications(
    job_post_id: uuid.UUID | None = None,
    status: ApplicationStatus | None = None,
    db: AsyncSession = Depends(get_db),
    service: ApplicationService = Depends(get_application_service),
) -> Page[ApplicationReviewOut]:
    query = await service.list_for_review(job_post_id=job_post_id, status=status)
    return await apaginate(
        db,
        query,
        transformer=lambda rows: [ApplicationReviewOut.model_validate(r) for r in rows],
    )


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: uuid.UUID,
    current_user: auth_entities.User = Depends(get_current_user),
    service: ApplicationService = Depends(get_application_service),
) -> ApplicationOut:
    return await service.get(application_id, current_user)


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
