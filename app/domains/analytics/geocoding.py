"""On-demand geocoding of free-text applicant locations (the standardized
`application_evaluations.location` field — see evaluations/dimensions.py's
LOCATION_FORMAT_HINT) via Nominatim, OpenStreetMap's public geocoder, for the
locations heatmap on the analytics dashboard.

Results are cached forever in `geocoded_locations` (models.py) — a place
name's coordinates don't change, and Nominatim's usage policy caps the public
API at one request/second and asks for a descriptive User-Agent. Both matter
here since this can run inline in an admin dashboard request: after the first
load resolves a location, every later load for it is a cache hit and never
touches the network.
"""

import asyncio
import time

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.analytics.models import GeocodedLocation

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "ats-analytics/1.0 (internal HR analytics dashboard)"
_MIN_INTERVAL_SECONDS = 1.0

# Module-level: one process-wide throttle, since Nominatim's 1 req/sec limit
# is per-client (by User-Agent/IP), not per-request.
_last_request_at = 0.0
_throttle_lock = asyncio.Lock()


def normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


# The AI is told to write "Remote" for no-fixed-location applicants (see
# evaluations/dimensions.py's LOCATION_FORMAT_HINT) — that's not a place to
# geocode. Left un-skipped, Nominatim's free-text search can match it to an
# actual, unrelated town named "Remote" (e.g. Remote, Oregon, USA) and plot a
# misleading point on the heatmap.
_NOT_A_PLACE = frozenset({"remote", "n/a", "na", "none", "unknown", "unspecified"})


async def _throttle() -> None:
    global _last_request_at
    async with _throttle_lock:
        wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()


async def _fetch_from_nominatim(query: str) -> tuple[float, float, str] | None:
    await _throttle()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(
                _NOMINATIM_URL,
                params={"q": query, "format": "jsonv2", "limit": 1},
                headers={"User-Agent": _USER_AGENT},
            )
            res.raise_for_status()
            results = res.json()
    except (httpx.HTTPError, ValueError):
        # Network hiccup or bad JSON — leave it uncached so the next load
        # retries, rather than caching a permanent miss for a transient fault.
        return None
    if not results:
        return None
    hit = results[0]
    try:
        return float(hit["lat"]), float(hit["lon"]), str(hit.get("display_name", query))
    except (KeyError, TypeError, ValueError):
        return None


async def geocode_many(
    db: AsyncSession, texts: list[str]
) -> dict[str, tuple[float, float] | None]:
    """Resolves each of `texts` to (lat, lng), or None if unresolvable
    (typo, "Remote", a query Nominatim genuinely has nothing for) — cache
    first, Nominatim only for queries never seen before."""
    by_query: dict[str, str] = {}
    for text in texts:
        if text.strip():
            by_query.setdefault(normalize(text), text)
    if not by_query:
        return {}

    cached = (
        await db.execute(
            select(GeocodedLocation).where(GeocodedLocation.query.in_(by_query))
        )
    ).scalars().all()
    resolved: dict[str, tuple[float, float] | None] = {
        row.query: (
            (row.latitude, row.longitude)
            if row.latitude is not None and row.longitude is not None
            else None
        )
        for row in cached
    }

    for query in by_query:
        if query in _NOT_A_PLACE:
            resolved[query] = None

    new_queries = [q for q in by_query if q not in resolved]
    for query in new_queries:
        hit = await _fetch_from_nominatim(query)
        db.add(
            GeocodedLocation(
                query=query,
                latitude=hit[0] if hit else None,
                longitude=hit[1] if hit else None,
                display_name=hit[2] if hit else None,
            )
        )
        resolved[query] = (hit[0], hit[1]) if hit else None
    if new_queries:
        await db.commit()

    return {
        text: resolved[normalize(text)] for text in texts if normalize(text) in resolved
    }
