import uuid

from app.domains.analytics.repository import AnalyticsRepository


class AnalyticsService:
    def __init__(self, analytics: AnalyticsRepository):
        self.analytics = analytics

    async def overview(
        self,
        *,
        period: str,
        position_id: uuid.UUID | None,
    ) -> dict:
        return await self.analytics.overview(period=period, position_id=position_id)
