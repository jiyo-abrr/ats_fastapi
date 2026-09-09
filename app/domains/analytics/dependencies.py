from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.analytics.repository import AnalyticsRepository
from app.domains.analytics.service import AnalyticsService


def get_analytics_repository(
    db: AsyncSession = Depends(get_db),
) -> AnalyticsRepository:
    return AnalyticsRepository(db)


def get_analytics_service(
    analytics: AnalyticsRepository = Depends(get_analytics_repository),
) -> AnalyticsService:
    return AnalyticsService(analytics)
