"""Tests for rate limits and geoip API routes."""

import pytest

from app.models.rate_limit import RateLimitRule, GeoipRule, GeoipSettings


class TestRateLimitsRoutes:
    """Tests for /api/rate-limits endpoints."""

    @pytest.mark.asyncio
    async def test_list_rate_limits(self, client, admin_user, auth_headers):
        response = await client.get("/api/rate-limits", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_create_rate_limit(self, client, admin_user, auth_headers):
        response = await client.post("/api/rate-limits", headers=auth_headers, json={
            "name": "Test Rate Limit",
            "requests_per_minute": 60,
            "burst_size": 10,
            "action": "reject",
        })
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["name"] == "Test Rate Limit"

    @pytest.mark.asyncio
    async def test_get_rate_limit(self, client, admin_user, auth_headers, db_session):
        rule = RateLimitRule(
            id="rl-test-1",
            name="Test RL",
            requests_per_minute=100,
            burst_size=10,
            action="reject",
        )
        db_session.add(rule)
        await db_session.commit()

        response = await client.get("/api/rate-limits/rl-test-1", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_rate_limit(self, client, admin_user, auth_headers, db_session):
        rule = RateLimitRule(
            id="rl-del-1",
            name="Delete Me",
            requests_per_minute=100,
            burst_size=10,
            action="reject",
        )
        db_session.add(rule)
        await db_session.commit()

        response = await client.delete("/api/rate-limits/rl-del-1", headers=auth_headers)
        assert response.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_rate_limits_no_auth(self, client):
        response = await client.get("/api/rate-limits")
        assert response.status_code == 403


class TestGeoipRoutes:
    """Tests for /api/geoip endpoints."""

    @pytest.mark.asyncio
    async def test_get_geoip_settings(self, client, admin_user, auth_headers):
        response = await client.get("/api/geoip/settings", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_geoip_rules(self, client, admin_user, auth_headers):
        response = await client.get("/api/geoip/rules", headers=auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_create_geoip_rule(self, client, admin_user, auth_headers):
        response = await client.post("/api/geoip/rules", headers=auth_headers, json={
            "name": "Block Test Countries",
            "mode": "blocklist",
            "countries": '["XX", "YY"]',
            "action": "block",
        })
        assert response.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_geoip_no_auth(self, client):
        response = await client.get("/api/geoip/settings")
        assert response.status_code == 403
