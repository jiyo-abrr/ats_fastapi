from unittest.mock import AsyncMock, patch

import pytest

from app.domains.analytics.geocoding import GeocodingService
from app.domains.analytics.geocoding_client import GeocodingUnavailable


def make_service(cached=None):
    cache, uow = AsyncMock(), AsyncMock()
    cache.get_many.return_value = cached or {}
    return GeocodingService(cache, uow), cache, uow


async def test_remote_never_hits_provider():
    service, cache, uow = make_service()
    with patch("app.domains.analytics.geocoding.fetch_coordinates") as fetch:
        result = await service.geocode_many(["Remote", "  REMOTE  ", "N/A", " "])
    fetch.assert_not_called()
    cache.store.assert_not_awaited()
    uow.commit.assert_not_awaited()
    assert result == {"Remote": None, "  REMOTE  ": None, "N/A": None}


async def test_cache_hits_and_duplicate_names_do_not_fetch_twice():
    service, cache, uow = make_service({"manila": (14.6, 121.0)})
    with patch("app.domains.analytics.geocoding.fetch_coordinates") as fetch:
        result = await service.geocode_many(["Manila", " MANILA "])
    fetch.assert_not_called()
    cache.store.assert_not_awaited()
    uow.commit.assert_not_awaited()
    assert result == {"Manila": (14.6, 121.0), " MANILA ": (14.6, 121.0)}


@pytest.mark.parametrize("hit", [(14.676, 121.0437, "Quezon City"), None])
async def test_success_and_definitive_miss_are_cached_once(hit):
    service, cache, uow = make_service()
    with patch(
        "app.domains.analytics.geocoding.fetch_coordinates",
        new=AsyncMock(return_value=hit),
    ) as fetch:
        result = await service.geocode_many(["Quezon City", "QUEZON CITY"])
    fetch.assert_awaited_once_with("quezon city")
    cache.store.assert_awaited_once_with("quezon city", hit)
    uow.commit.assert_awaited_once()
    assert result["Quezon City"] == (hit[:2] if hit else None)


async def test_provider_failure_is_not_cached_and_next_request_retries():
    service, cache, uow = make_service()
    with patch(
        "app.domains.analytics.geocoding.fetch_coordinates",
        new=AsyncMock(side_effect=[GeocodingUnavailable(), (14.6, 121.0, "Manila")]),
    ) as fetch:
        assert await service.geocode_many(["Manila"]) == {"Manila": None}
        cache.store.assert_not_awaited()
        uow.commit.assert_not_awaited()
        assert await service.geocode_many(["Manila"]) == {"Manila": (14.6, 121.0)}
    assert fetch.await_count == 2
    cache.store.assert_awaited_once()
    uow.commit.assert_awaited_once()


async def test_failed_cache_commit_rolls_back():
    service, _cache, uow = make_service()
    uow.commit.side_effect = RuntimeError("database unavailable")
    with (
        patch(
            "app.domains.analytics.geocoding.fetch_coordinates",
            new=AsyncMock(return_value=None),
        ),
        pytest.raises(RuntimeError),
    ):
        await service.geocode_many(["Manila"])
    uow.rollback.assert_awaited_once()
