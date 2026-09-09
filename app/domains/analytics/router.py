import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.domains.analytics.dependencies import get_analytics_service
from app.domains.analytics.schemas import AnalyticsOverviewOut
from app.domains.analytics.service import AnalyticsService
from app.domains.rbac.dependencies import require_admin

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_admin)],
)


@router.get("/overview", response_model=AnalyticsOverviewOut)
async def analytics_overview(
    period: Literal["30d", "90d", "all"] = Query("90d"),
    position_id: uuid.UUID | None = None,
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsOverviewOut:
    return AnalyticsOverviewOut(
        **await service.overview(period=period, position_id=position_id)
    )
