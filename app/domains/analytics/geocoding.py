"""Application-level geocoding with explicit cache transaction ownership."""

from app.core.unit_of_work import UnitOfWork
from app.domains.analytics.geocoding_client import (
    GeocodingUnavailable,
    fetch_coordinates,
)
from app.domains.analytics.geocoding_repository import GeocodingCacheRepository

_NOT_A_PLACE = frozenset({"remote", "n/a", "na", "none", "unknown", "unspecified"})


def normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


class GeocodingService:
    def __init__(self, cache: GeocodingCacheRepository, uow: UnitOfWork):
        self.cache = cache
        self.uow = uow

    async def geocode_many(
        self, texts: list[str]
    ) -> dict[str, tuple[float, float] | None]:
        queries = list(dict.fromkeys(normalize(t) for t in texts if t.strip()))
        if not queries:
            return {}
        resolved = dict(await self.cache.get_many(queries))
        resolved.update({q: None for q in queries if q in _NOT_A_PLACE})
        changed = False
        try:
            for query in queries:
                if query in resolved:
                    continue
                try:
                    hit = await fetch_coordinates(query)
                except GeocodingUnavailable:
                    resolved[query] = None
                    continue
                await self.cache.store(query, hit)
                changed = True
                resolved[query] = (hit[0], hit[1]) if hit else None
            if changed:
                await self.uow.commit()
        except Exception:
            await self.uow.rollback()
            raise
        return {text: resolved[normalize(text)] for text in texts if text.strip()}
