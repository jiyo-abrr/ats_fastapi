"""Persistence for the analytics cache; the caller owns the transaction."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.models import GeocodedLocation


class GeocodingCacheRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_many(
        self, queries: list[str]
    ) -> dict[str, tuple[float, float] | None]:
        rows = (
            await self.db.execute(
                select(
                    GeocodedLocation.query,
                    GeocodedLocation.latitude,
                    GeocodedLocation.longitude,
                ).where(GeocodedLocation.query.in_(queries))
            )
        ).all()
        return {
            query: (lat, lon) if lat is not None and lon is not None else None
            for query, lat, lon in rows
        }

    async def store(self, query: str, hit: tuple[float, float, str] | None) -> None:
        # Concurrent dashboard loads may resolve the same uncached location.
        await self.db.execute(
            insert(GeocodedLocation)
            .values(
                query=query,
                latitude=hit[0] if hit else None,
                longitude=hit[1] if hit else None,
                display_name=hit[2][:200] if hit else None,
            )
            .on_conflict_do_nothing(index_elements=[GeocodedLocation.query])
        )
