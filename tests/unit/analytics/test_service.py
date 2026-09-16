import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.domains.analytics.service import AnalyticsService

pytestmark = pytest.mark.asyncio


async def test_overview_forwards_period_and_position():
    repo = AsyncMock()
    repo.overview.return_value = {"period": "daily"}
    service = AnalyticsService(repo, AsyncMock())
    position_id = uuid.uuid4()

    result = await service.overview(period="daily", position_id=position_id)

    assert result == {"period": "daily"}
    repo.overview.assert_awaited_once_with(period="daily", position_id=position_id)


async def test_locations_attaches_geocoded_coordinates():
    repo = AsyncMock()
    repo.location_counts.return_value = [
        {"key": "Quezon City, Metro Manila", "count": 3},
        {"key": "Some Unresolvable Place", "count": 1},
    ]
    db = AsyncMock()
    service = AnalyticsService(repo, db)

    with patch(
        "app.domains.analytics.service.geocoding.geocode_many",
        new=AsyncMock(
            return_value={
                "Quezon City, Metro Manila": (14.6760, 121.0437),
                "Some Unresolvable Place": None,
            }
        ),
    ) as mocked_geocode:
        result = await service.locations(position_id=None)

    mocked_geocode.assert_awaited_once_with(
        db, ["Quezon City, Metro Manila", "Some Unresolvable Place"]
    )
    assert result == [
        {
            "key": "Quezon City, Metro Manila",
            "count": 3,
            "latitude": 14.6760,
            "longitude": 121.0437,
        },
        {
            "key": "Some Unresolvable Place",
            "count": 1,
            "latitude": None,
            "longitude": None,
        },
    ]
