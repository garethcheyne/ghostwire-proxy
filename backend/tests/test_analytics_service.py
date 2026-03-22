"""Tests for analytics service — hourly/daily/geo aggregation."""

import pytest
from datetime import datetime, timezone, timedelta

from app.services.analytics_service import (
    aggregate_hourly,
    aggregate_daily,
    aggregate_geo,
)


class TestAggregateHourly:
    """Tests for hourly aggregation."""

    @pytest.mark.asyncio
    async def test_aggregate_no_data(self, db_session):
        count = await aggregate_hourly(db_session, hours_back=2)
        assert count == 0

    @pytest.mark.asyncio
    async def test_aggregate_hourly_returns_int(self, db_session):
        result = await aggregate_hourly(db_session)
        assert isinstance(result, int)


class TestAggregateDaily:
    """Tests for daily aggregation."""

    @pytest.mark.asyncio
    async def test_aggregate_no_data(self, db_session):
        count = await aggregate_daily(db_session, days_back=2)
        assert count == 0


class TestAggregateGeo:
    """Tests for geo aggregation."""

    @pytest.mark.asyncio
    async def test_aggregate_no_data(self, db_session):
        count = await aggregate_geo(db_session, days_back=2)
        assert count == 0
