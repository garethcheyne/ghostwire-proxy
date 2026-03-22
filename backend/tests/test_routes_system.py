"""Tests for system API routes."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestSystemStatus:
    """Tests for GET /api/system/status."""

    @pytest.mark.asyncio
    async def test_get_system_status(self, client, admin_user, auth_headers):
        with patch("app.services.system_service.system_monitor_service.get_system_status",
                   new_callable=AsyncMock, return_value={
                       "timestamp": "2026-01-01T00:00:00Z",
                       "services": {"api": {"status": "healthy"}},
                       "resources": {
                           "cpu": {"usage": 10.0, "cores": 4},
                           "memory": {"used": 1000, "total": 8000, "percent": 12.5, "available": 7000},
                           "disk": {"used": 5000, "total": 50000, "percent": 10.0, "free": 45000},
                       },
                       "containers": [],
                       "database": {"size_bytes": None, "connections": None, "table_counts": None},
                   }):
            response = await client.get("/api/system/status", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "timestamp" in data
        assert "services" in data
        assert "resources" in data

    @pytest.mark.asyncio
    async def test_system_status_no_auth(self, client):
        response = await client.get("/api/system/status")
        assert response.status_code == 403


class TestSystemMetrics:
    """Tests for GET /api/system/metrics."""

    @pytest.mark.asyncio
    async def test_get_metrics(self, client, admin_user, auth_headers):
        with patch("app.services.system_service.system_monitor_service.get_metrics_history",
                   new_callable=AsyncMock, return_value=[]):
            response = await client.get("/api/system/metrics?period=1h", headers=auth_headers)

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_get_metrics_invalid_period(self, client, admin_user, auth_headers):
        response = await client.get("/api/system/metrics?period=invalid", headers=auth_headers)
        assert response.status_code == 422


class TestSystemThroughput:
    """Tests for GET /api/system/throughput."""

    @pytest.mark.asyncio
    async def test_get_throughput(self, client, admin_user, auth_headers):
        with patch("app.services.system_service.system_monitor_service.get_traffic_throughput",
                   new_callable=AsyncMock, return_value=[]):
            response = await client.get("/api/system/throughput?period=1h", headers=auth_headers)

        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestHealthCheck:
    """Tests for GET /health."""

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
