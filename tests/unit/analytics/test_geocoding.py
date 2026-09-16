from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.analytics import geocoding

pytestmark = pytest.mark.asyncio


def _empty_scalars(db: AsyncMock) -> None:
    """A cache lookup that finds nothing — the common case in these tests.

    `db.execute(...)` is async, but the `Result` it returns is a plain
    (sync) object — an AsyncMock would wrongly make `.scalars()` itself
    async, so the result object must be a MagicMock, not an AsyncMock."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    # AsyncSession.add() is sync in real SQLAlchemy — an AsyncMock default
    # would wrongly make it async and leave an unawaited-coroutine warning.
    db.add = MagicMock()


async def test_remote_never_hits_nominatim():
    db = AsyncMock()
    _empty_scalars(db)

    with patch(
        "app.domains.analytics.geocoding._fetch_from_nominatim", new=AsyncMock()
    ) as fetch:
        result = await geocoding.geocode_many(db, ["Remote", "  REMOTE  ", "N/A"])

    fetch.assert_not_awaited()
    assert result == {"Remote": None, "  REMOTE  ": None, "N/A": None}
    db.commit.assert_not_awaited()


async def test_a_real_place_is_resolved_via_nominatim():
    db = AsyncMock()
    _empty_scalars(db)

    with patch(
        "app.domains.analytics.geocoding._fetch_from_nominatim",
        new=AsyncMock(return_value=(14.676, 121.0437, "Quezon City, Philippines")),
    ) as fetch:
        result = await geocoding.geocode_many(db, ["Quezon City, Metro Manila"])

    fetch.assert_awaited_once_with("quezon city, metro manila")
    assert result == {"Quezon City, Metro Manila": (14.676, 121.0437)}
    db.commit.assert_awaited_once()
