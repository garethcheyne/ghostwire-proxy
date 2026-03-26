"""Tests for per-host scoping of WAF rules, rate limits, GeoIP rules, and honeypot traps."""

import pytest
from app.models.proxy_host import ProxyHost
from app.models.waf import WafRule
from app.models.rate_limit import RateLimitRule, GeoipRule
from app.models.honeypot import HoneypotTrap


@pytest.fixture
async def proxy_host(db_session):
    """Create a proxy host for per-host tests."""
    host = ProxyHost(
        id="ph-perhost-1",
        domain_names=["perhost.example.com"],
        forward_scheme="http",
        forward_host="backend",
        forward_port=80,
    )
    db_session.add(host)
    await db_session.commit()
    return host


@pytest.fixture
async def proxy_host_b(db_session):
    """Create a second proxy host for isolation tests."""
    host = ProxyHost(
        id="ph-perhost-2",
        domain_names=["other.example.com"],
        forward_scheme="http",
        forward_host="backend2",
        forward_port=80,
    )
    db_session.add(host)
    await db_session.commit()
    return host


class TestWafRulesPerHost:
    """Test WAF rules per-host scoping."""

    @pytest.mark.asyncio
    async def test_create_waf_rule_global(self, client, admin_user, auth_headers):
        """WAF rule without proxy_host_id is global."""
        response = await client.post("/api/waf/rules", headers=auth_headers, json={
            "name": "Global SQLi Rule",
            "category": "sqli",
            "pattern": "union.*select",
            "severity": "high",
            "action": "block",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["proxy_host_id"] is None

    @pytest.mark.asyncio
    async def test_create_waf_rule_per_host(self, client, admin_user, auth_headers, proxy_host):
        """WAF rule with proxy_host_id is scoped to that host."""
        response = await client.post("/api/waf/rules", headers=auth_headers, json={
            "name": "Host-Specific XSS Rule",
            "category": "xss",
            "pattern": "<script",
            "severity": "high",
            "action": "block",
            "proxy_host_id": proxy_host.id,
        })
        assert response.status_code == 201
        data = response.json()
        assert data["proxy_host_id"] == proxy_host.id

    @pytest.mark.asyncio
    async def test_list_waf_rules_filter_by_host(self, client, admin_user, auth_headers, db_session, proxy_host):
        """Listing WAF rules with proxy_host_id filter returns only matching rules."""
        global_rule = WafRule(id="waf-global-1", name="Global Rule", category="sqli",
                             pattern="drop.*table", severity="high", action="block")
        host_rule = WafRule(id="waf-host-1", name="Host Rule", category="xss",
                           pattern="<img.*onerror", severity="medium", action="log",
                           proxy_host_id=proxy_host.id)
        db_session.add_all([global_rule, host_rule])
        await db_session.commit()

        # Filter by host
        response = await client.get(f"/api/waf/rules?proxy_host_id={proxy_host.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        ids = [r["id"] for r in data]
        assert "waf-host-1" in ids
        assert "waf-global-1" not in ids

        # No filter returns all
        response = await client.get("/api/waf/rules", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        ids = [r["id"] for r in data]
        assert "waf-global-1" in ids
        assert "waf-host-1" in ids


class TestRateLimitsPerHost:
    """Test rate limit rules per-host scoping."""

    @pytest.mark.asyncio
    async def test_create_rate_limit_with_host(self, client, admin_user, auth_headers, proxy_host):
        """Rate limit with proxy_host_id is scoped to that host."""
        response = await client.post("/api/rate-limits", headers=auth_headers, json={
            "name": "Host Rate Limit",
            "requests_per_minute": 30,
            "burst_size": 5,
            "action": "reject",
            "proxy_host_id": proxy_host.id,
        })
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["proxy_host_id"] == proxy_host.id

    @pytest.mark.asyncio
    async def test_list_rate_limits_filter_by_host(self, client, admin_user, auth_headers, db_session, proxy_host):
        """Rate limit listing respects proxy_host_id filter."""
        global_rl = RateLimitRule(id="rl-global-ph", name="Global RL",
                                 requests_per_minute=100, burst_size=10, action="reject")
        host_rl = RateLimitRule(id="rl-host-ph", name="Host RL",
                               requests_per_minute=30, burst_size=5, action="reject",
                               proxy_host_id=proxy_host.id)
        db_session.add_all([global_rl, host_rl])
        await db_session.commit()

        response = await client.get(f"/api/rate-limits?proxy_host_id={proxy_host.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        ids = [r["id"] for r in data]
        assert "rl-host-ph" in ids
        assert "rl-global-ph" not in ids


class TestGeoipPerHost:
    """Test GeoIP rules per-host scoping."""

    @pytest.mark.asyncio
    async def test_create_geoip_rule_with_host(self, client, admin_user, auth_headers, proxy_host):
        """GeoIP rule with proxy_host_id is scoped to that host."""
        response = await client.post("/api/geoip/rules", headers=auth_headers, json={
            "name": "Host GeoIP Block",
            "mode": "blocklist",
            "countries": '["CN", "RU"]',
            "action": "block",
            "proxy_host_id": proxy_host.id,
        })
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["proxy_host_id"] == proxy_host.id

    @pytest.mark.asyncio
    async def test_list_geoip_rules_filter_by_host(self, client, admin_user, auth_headers, db_session, proxy_host):
        """GeoIP listing respects proxy_host_id filter."""
        global_geo = GeoipRule(id="geo-global-ph", name="Global Geo",
                               mode="blocklist", countries='["XX"]', action="block")
        host_geo = GeoipRule(id="geo-host-ph", name="Host Geo",
                             mode="blocklist", countries='["YY"]', action="block",
                             proxy_host_id=proxy_host.id)
        db_session.add_all([global_geo, host_geo])
        await db_session.commit()

        response = await client.get(f"/api/geoip/rules?proxy_host_id={proxy_host.id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        ids = [r["id"] for r in data]
        assert "geo-host-ph" in ids
        assert "geo-global-ph" not in ids


class TestHoneypotPerHost:
    """Test honeypot traps per-host scoping."""

    @pytest.mark.asyncio
    async def test_create_trap_global(self, client, admin_user, auth_headers):
        """Honeypot trap without proxy_host_id is global."""
        response = await client.post("/api/honeypot/traps", headers=auth_headers, json={
            "path": "/wp-admin-global",
            "name": "Global WP Trap",
            "trap_type": "wordpress",
            "severity": "high",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["proxy_host_id"] is None

    @pytest.mark.asyncio
    async def test_create_trap_per_host(self, client, admin_user, auth_headers, proxy_host):
        """Honeypot trap with proxy_host_id is scoped to that host."""
        response = await client.post("/api/honeypot/traps", headers=auth_headers, json={
            "path": "/wp-admin-host",
            "name": "Host WP Trap",
            "trap_type": "wordpress",
            "severity": "high",
            "proxy_host_id": proxy_host.id,
        })
        assert response.status_code == 201
        data = response.json()
        assert data["proxy_host_id"] == proxy_host.id

    @pytest.mark.asyncio
    async def test_duplicate_trap_same_host_rejected(self, client, admin_user, auth_headers, proxy_host):
        """Cannot create two traps with same path on the same host."""
        payload = {
            "path": "/duplicate-test",
            "name": "Dup Trap",
            "trap_type": "generic",
            "severity": "medium",
            "proxy_host_id": proxy_host.id,
        }
        r1 = await client.post("/api/honeypot/traps", headers=auth_headers, json=payload)
        assert r1.status_code == 201

        r2 = await client.post("/api/honeypot/traps", headers=auth_headers, json=payload)
        assert r2.status_code in (400, 409)

    @pytest.mark.asyncio
    async def test_same_path_different_hosts_allowed(self, client, admin_user, auth_headers, proxy_host, proxy_host_b):
        """Same path can exist on different hosts."""
        payload_a = {
            "path": "/shared-path",
            "name": "Trap A",
            "trap_type": "generic",
            "severity": "medium",
            "proxy_host_id": proxy_host.id,
        }
        payload_b = {
            "path": "/shared-path",
            "name": "Trap B",
            "trap_type": "generic",
            "severity": "medium",
            "proxy_host_id": proxy_host_b.id,
        }
        r1 = await client.post("/api/honeypot/traps", headers=auth_headers, json=payload_a)
        assert r1.status_code == 201
        r2 = await client.post("/api/honeypot/traps", headers=auth_headers, json=payload_b)
        assert r2.status_code == 201
