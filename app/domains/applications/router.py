import uuid

from fastapi import APIRouter, Depends, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.applications.dependencies import (
    get_application_repository,
    get_application_service,
)
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.repository import ApplicationRepository
from app.domains.applications.schemas import (
    ApplicationCreate,
    ApplicationOut,
    ApplicationReviewOut,
    ApplicationStatusUpdate,
    ApplicationSummaryOut,
)
from app.domains.applications.service import ApplicationService
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
) -> ApplicationOut:
    return await service.create(
        job_post_id=payload.job_post_id, current_user=current_user
    )


@router.get("/me", response_model=Page[ApplicationSummaryOut])
async def list_my_applications(
    current_user: auth_entities.User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    repo: ApplicationRepository = Depends(get_application_repository),
) -> Page[ApplicationSummaryOut]:
    query = await repo.list_for_applicant(current_user.id)
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
    repo: ApplicationRepository = Depends(get_application_repository),
) -> Page[ApplicationReviewOut]:
    query = await repo.list_for_review(job_post_id=job_post_id, status=status)
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
