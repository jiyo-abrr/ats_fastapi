import uuid
from unittest.mock import AsyncMock

import pytest

from app.domains.analytics.service import AnalyticsService

pytestmark = pytest.mark.asyncio


async def test_overview_forwards_period_and_position():
    repo = AsyncMock()
    repo.overview.return_value = {"period": "30d"}
    service = AnalyticsService(repo)
    position_id = uuid.uuid4()

    result = await service.overview(period="30d", position_id=position_id)

    assert result == {"period": "30d"}
    repo.overview.assert_awaited_once_with(period="30d", position_id=position_id)
