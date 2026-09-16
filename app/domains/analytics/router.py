import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.domains.analytics.dependencies import get_analytics_service
from app.domains.analytics.schemas import AnalyticsOverviewOut, LocationCountOut
from app.domains.analytics.service import AnalyticsService
from app.domains.rbac.dependencies import require_admin

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_admin)],
)


@router.get("/overview", response_model=AnalyticsOverviewOut)
async def analytics_overview(
    period: Literal["daily", "weekly", "monthly", "yearly"] = Query("daily"),
    position_id: uuid.UUID | None = None,
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsOverviewOut:
    return AnalyticsOverviewOut(
        **await service.overview(period=period, position_id=position_id)
    )


@router.get("/locations", response_model=list[LocationCountOut])
async def analytics_locations(
    position_id: uuid.UUID | None = None,
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[LocationCountOut]:
    """Ranked applicant-location counts + coordinates (geocoded via
    Nominatim, cached) for the locations bar chart and heatmap. Separate from
    /overview so a cold geocoding cache doesn't stall the rest of the
    dashboard."""
    return [
        LocationCountOut(**row)
        for row in await service.locations(position_id=position_id)
    ]
