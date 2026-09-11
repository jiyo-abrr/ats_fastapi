from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.interviews.availability_repository import (
    InterviewAvailabilityRepository,
)
from app.domains.interviews.availability_service import InterviewAvailabilityService
from app.domains.interviews.repository import InterviewRepository
from app.domains.interviews.scheduling_service import InterviewService


def get_interview_repository(
    db: AsyncSession = Depends(get_db),
) -> InterviewRepository:
    return InterviewRepository(db)


def get_interview_availability_repository(
    db: AsyncSession = Depends(get_db),
) -> InterviewAvailabilityRepository:
    return InterviewAvailabilityRepository(db)


def get_interview_availability_service(
    availability: InterviewAvailabilityRepository = Depends(
        get_interview_availability_repository
    ),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> InterviewAvailabilityService:
    return InterviewAvailabilityService(availability, uow)


def get_interview_service(
    interviews: InterviewRepository = Depends(get_interview_repository),
    availability: InterviewAvailabilityService = Depends(
        get_interview_availability_service
    ),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> InterviewService:
    return InterviewService(interviews, availability, uow)
