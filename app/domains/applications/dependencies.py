from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.applications.evaluations import EvaluationService
from app.domains.applications.interview_availability import (
    InterviewAvailabilityService,
)
from app.domains.applications.interviews import InterviewService
from app.domains.applications.repository import ApplicationRepository
from app.domains.applications.service import ApplicationService
from app.domains.job_posts.dependencies import get_job_post_repository
from app.domains.job_posts.repository import JobPostRepository
from app.domains.rbac.dependencies import get_role_permission_repository
from app.domains.rbac.repository import RolePermissionRepository


def get_application_repository(
    db: AsyncSession = Depends(get_db),
) -> ApplicationRepository:
    return ApplicationRepository(db)


def get_application_service(
    applications: ApplicationRepository = Depends(get_application_repository),
    job_posts: JobPostRepository = Depends(get_job_post_repository),
    role_permissions: RolePermissionRepository = Depends(
        get_role_permission_repository
    ),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> ApplicationService:
    return ApplicationService(applications, job_posts, role_permissions, uow)


def get_evaluation_service(
    db: AsyncSession = Depends(get_db),
) -> EvaluationService:
    return EvaluationService(db)


def get_interview_service(
    db: AsyncSession = Depends(get_db),
) -> InterviewService:
    return InterviewService(db)


def get_interview_availability_service(
    db: AsyncSession = Depends(get_db),
) -> InterviewAvailabilityService:
    return InterviewAvailabilityService(db)
