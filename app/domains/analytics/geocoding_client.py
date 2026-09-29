"""External geocoding adapter. Transient failures are not cacheable misses."""

import asyncio
import time

import httpx

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_USER_AGENT = "ats-analytics/1.0 (internal HR analytics dashboard)"
_MIN_INTERVAL_SECONDS = 1.0
_last_request_at = 0.0
_throttle_lock = asyncio.Lock()


class GeocodingUnavailable(Exception):
    """The provider could not supply a reliable lookup result."""


async def _throttle() -> None:
    global _last_request_at
    async with _throttle_lock:
        wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()


async def fetch_coordinates(query: str) -> tuple[float, float, str] | None:
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
    except httpx.HTTPError, ValueError:
        # Network hiccup or bad JSON — leave it uncached so the next load
        # retries, rather than caching a permanent miss for a transient fault.
        raise GeocodingUnavailable from None
    if not isinstance(results, list):
        raise GeocodingUnavailable
    if not results:
        return None
    hit = results[0]
    try:
        return float(hit["lat"]), float(hit["lon"]), str(hit.get("display_name", query))
    except KeyError, TypeError, ValueError:
        raise GeocodingUnavailable from None
