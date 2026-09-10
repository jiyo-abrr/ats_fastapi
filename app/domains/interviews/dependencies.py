from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.interviews.availability_service import InterviewAvailabilityService
from app.domains.interviews.scheduling_service import InterviewService


def get_interview_service(
    db: AsyncSession = Depends(get_db),
) -> InterviewService:
    return InterviewService(db)


def get_interview_availability_service(
    db: AsyncSession = Depends(get_db),
) -> InterviewAvailabilityService:
    return InterviewAvailabilityService(db)
