"""Tests for system monitor service."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.system_service import SystemMonitorService


class TestSystemMonitorService:
    """Tests for system monitoring."""

    @pytest.mark.asyncio
    async def test_get_system_status(self):
        svc = SystemMonitorService()
        with patch("psutil.cpu_percent", return_value=25.0), \
             patch("psutil.cpu_count", return_value=4), \
             patch("psutil.virtual_memory", return_value=MagicMock(
                 total=8 * 1024**3, used=4 * 1024**3,
                 percent=50.0, available=4 * 1024**3
             )), \
             patch("psutil.disk_usage", return_value=MagicMock(
                 total=100 * 1024**3, used=50 * 1024**3,
                 percent=50.0, free=50 * 1024**3
             )), \
             patch("psutil.net_io_counters", return_value=MagicMock(
                 bytes_sent=1000, bytes_recv=2000
             )), \
             patch.object(svc, "_get_services_health", new_callable=AsyncMock, return_value={
                 "api": {"status": "healthy"}
             }), \
             patch.object(svc, "_get_container_info", new_callable=AsyncMock, return_value=[]), \
             patch.object(svc, "_get_database_stats", new_callable=AsyncMock, return_value={
                 "size_bytes": None, "connections": None, "table_counts": None
             }):
            status = await svc.get_system_status()

        assert "timestamp" in status
        assert "resources" in status
        assert "services" in status

    @pytest.mark.asyncio
    async def test_get_metrics_history(self, db_session):
        svc = SystemMonitorService()
        metrics = await svc.get_metrics_history("1h", db_session)
        assert isinstance(metrics, list)

    @pytest.mark.asyncio
    async def test_get_traffic_throughput(self, db_session):
        svc = SystemMonitorService()
        throughput = await svc.get_traffic_throughput("1h", db_session)
        assert isinstance(throughput, list)
