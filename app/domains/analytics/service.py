import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics import geocoding
from app.domains.analytics.repository import AnalyticsRepository


class AnalyticsService:
    def __init__(self, analytics: AnalyticsRepository, db: AsyncSession):
        self.analytics = analytics
        self.db = db

    async def overview(
        self,
        *,
        period: str,
        position_id: uuid.UUID | None,
    ) -> dict:
        return await self.analytics.overview(period=period, position_id=position_id)

    async def locations(self, *, position_id: uuid.UUID | None) -> list[dict]:
        """Ranked applicant-location counts + geocoded coordinates, for the
        analytics dashboard's locations bar chart and heatmap. Kept off the
        main /overview payload — geocoding a location never seen before hits
        Nominatim, rate-limited to 1/sec (see geocoding.py), which would
        otherwise stall the whole dashboard on a cold cache."""
        counts = await self.analytics.location_counts(position_id=position_id)
        coords = await geocoding.geocode_many(self.db, [c["key"] for c in counts])
        return [
            {
                **c,
                "latitude": (coords.get(c["key"]) or (None, None))[0],
                "longitude": (coords.get(c["key"]) or (None, None))[1],
            }
            for c in counts
        ]

    async def job_post_reports(self, *, position_id: uuid.UUID | None) -> list[dict]:
        return await self.analytics.job_post_reports(position_id=position_id)

    async def recruitment_insights(self, *, position_id: uuid.UUID | None) -> dict:
        return await self.analytics.recruitment_insights(position_id=position_id)

    async def recurring_applicants(
        self, *, position_id: uuid.UUID | None
    ) -> list[dict]:
        return await self.analytics.recurring_applicants(position_id=position_id)
