from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.analytics.geocoding import GeocodingService
from app.domains.analytics.geocoding_repository import GeocodingCacheRepository
from app.domains.analytics.repository import AnalyticsRepository
from app.domains.analytics.service import AnalyticsService


def get_analytics_repository(
    db: AsyncSession = Depends(get_db),
) -> AnalyticsRepository:
    return AnalyticsRepository(db)


def get_geocoding_service(
    db: AsyncSession = Depends(get_db),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> GeocodingService:
    return GeocodingService(GeocodingCacheRepository(db), uow)


def get_analytics_service(
    analytics: AnalyticsRepository = Depends(get_analytics_repository),
    geocoding: GeocodingService = Depends(get_geocoding_service),
) -> AnalyticsService:
    return AnalyticsService(analytics, geocoding)
