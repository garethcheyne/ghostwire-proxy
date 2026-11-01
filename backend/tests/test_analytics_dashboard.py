"""Analytics dashboard: rollup-backed totals and the raw-only top lists agree with the data."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.api.routes import analytics as analytics_routes
from app.core import cache
from app.core.cache import cache_delete_prefix, cached_json
from app.models.analytics import AnalyticsDaily
from app.models.proxy_host import ProxyHost
from app.models.traffic_log import TrafficLog
from app.services import traffic_rollup_service as rollup
from app.services.analytics_service import aggregate_daily
from sqlalchemy import select

from tests.conftest import TestSessionLocal

NOW = datetime.now(UTC).replace(microsecond=0)


@pytest.fixture(autouse=True)
async def _fresh_cache(monkeypatch):
    await cache_delete_prefix("analytics:")
    # The dashboard opens its own sessions; the app engine's pool would outlive
    # each test's event loop, the test engine is disposed after every test.
    monkeypatch.setattr(analytics_routes, "AsyncSessionLocal", TestSessionLocal)


def _log(host_id, minutes_ago, *, status=200, ip="198.51.100.7", uri="/", method="GET", ua="Mozilla/5.0 Firefox/1",
         country="NZ", referer=None, bytes_received=100):
    return TrafficLog(
        id=str(uuid.uuid4()),
        proxy_host_id=host_id,
        timestamp=NOW - timedelta(minutes=minutes_ago),
        client_ip=ip,
        request_method=method,
        request_uri=uri,
        status=status,
        response_time=40,
        bytes_sent=1000,
        bytes_received=bytes_received,
        country_code=country,
        country_name="New Zealand" if country == "NZ" else None,
        user_agent=ua,
        referer=referer,
    )


@pytest.fixture
async def hosts(db_session):
    a = ProxyHost(id=str(uuid.uuid4()), domain_names=["a.example.test"], forward_scheme="http",
                  forward_host="10.0.0.5", forward_port=8080)
    b = ProxyHost(id=str(uuid.uuid4()), domain_names=["b.example.test"], forward_scheme="http",
                  forward_host="10.0.0.6", forward_port=80)
    db_session.add_all([a, b])
    await db_session.flush()
    # Old enough to be rolled up (2 days ago) and recent tail (minutes ago).
    db_session.add_all(
        [
            _log(a.id, 2 * 24 * 60, ip="203.0.113.1", uri="/old", referer="https://ref.test/"),
            _log(a.id, 2 * 24 * 60 + 1, ip="203.0.113.2", uri="/old", status=404),
            _log(a.id, 5, ip="203.0.113.1", uri="/new", method="POST", ua="curl/8"),
            _log(b.id, 6, ip="203.0.113.3", uri="/new", status=503, country="AU", ua="python-requests"),
            # Previous 7-day period: counts toward the comparison only.
            _log(b.id, 9 * 24 * 60, ip="203.0.113.9"),
            # Older than both periods: shows raw data still covers the previous one.
            _log(b.id, 15 * 24 * 60, ip="203.0.113.10"),
        ]
    )
    await db_session.commit()
    await rollup.refresh(session_factory=TestSessionLocal)
    return a, b


class TestDashboard:
    @pytest.mark.asyncio
    async def test_totals_and_top_lists(self, client, auth_headers, hosts):
        a, b = hosts
        r = await client.get("/api/analytics/dashboard", headers=auth_headers, params={"period": "7d"})
        assert r.status_code == 200, r.text
        d = r.json()

        assert d["total_requests"] == 4
        assert d["total_unique_visitors"] == 3
        assert d["total_bytes_transferred"] == 4 * 1100
        assert d["status_breakdown"] == {"status_2xx": 2, "status_3xx": 0, "status_4xx": 1, "status_5xx": 1}
        assert d["error_rate"] == 50.0
        assert d["requests_change_percent"] == 300.0  # 4 vs 1
        assert d["visitors_change_percent"] == 200.0  # 3 vs 1
        assert d["requests_by_method"] == {"GET": 3, "POST": 1}
        assert sum(p["requests"] for p in d["time_series"]) == 4
        assert sum(h["requests"] for h in d["hourly_distribution"]) == 4

        top = {h["host_name"]: h for h in d["top_hosts"]}
        assert top["a.example.test"]["requests"] == 3
        assert top["a.example.test"]["unique_visitors"] == 2
        assert top["b.example.test"]["error_rate"] == 100.0

        assert {p["uri"]: p["requests"] for p in d["top_pages"]} == {"/old": 2, "/new": 2}
        assert d["top_referrers"] == [{"referer": "https://ref.test/", "requests": 1}]
        assert d["top_ips"][0] == {"ip": "203.0.113.1", "requests": 2, "country_code": "NZ",
                                   "country_name": "New Zealand"}
        assert {c["country"]: c["requests"] for c in d["country_stats"]} == {"NZ": 3, "AU": 1}
        assert {x["browser"]: x["requests"] for x in d["browser_stats"]} == {"Firefox": 2, "curl": 1, "Python": 1}
        assert {e["status"]: e["count"] for e in d["errors_by_status"]} == {404: 1, 503: 1}
        assert {e["host_name"] for e in d["errors_by_host"]} == {"a.example.test", "b.example.test"}

    @pytest.mark.asyncio
    async def test_no_comparison_before_retained_data(self, client, auth_headers, hosts):
        # 30d: the previous period (30-60 days ago) predates the oldest row.
        r = await client.get("/api/analytics/dashboard", headers=auth_headers, params={"period": "30d"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["requests_change_percent"] is None
        assert d["visitors_change_percent"] is None
        assert d["total_requests"] == 6

    @pytest.mark.asyncio
    async def test_raw_scan_timeout_keeps_rollup_figures(self, client, auth_headers, hosts, monkeypatch):
        monkeypatch.setitem(analytics_routes._RAW_TIMEOUT_MS, "7d", 1)
        r = await client.get("/api/analytics/dashboard", headers=auth_headers, params={"period": "7d"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_requests"] == 4
        assert d["top_pages"] == []
        assert d["total_unique_visitors"] == 0

    @pytest.mark.asyncio
    async def test_host_filter(self, client, auth_headers, hosts):
        a, _ = hosts
        r = await client.get(
            "/api/analytics/dashboard", headers=auth_headers, params={"period": "7d", "proxy_host_id": a.id}
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total_requests"] == 3
        assert d["total_unique_visitors"] == 2
        assert [h["host_name"] for h in d["top_hosts"]] == ["a.example.test"]


class TestAggregateDaily:
    @pytest.mark.asyncio
    async def test_bytes_beyond_int32(self, db_session, hosts):
        a, _ = hosts
        db_session.add(_log(a.id, 1, bytes_received=2_000_000_000))
        db_session.add(_log(a.id, 2, bytes_received=2_000_000_000))
        await db_session.commit()
        await aggregate_daily(db_session, days_back=1)
        rows = (await db_session.execute(select(AnalyticsDaily).where(AnalyticsDaily.proxy_host_id == a.id))).scalars()
        assert max(r.bytes_received for r in rows) >= 4_000_000_000


class TestCachedJsonSingleFlight:
    @pytest.mark.asyncio
    async def test_concurrent_misses_compute_once(self):
        calls = 0

        async def producer():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.05)
            return {"v": 1}

        results = await asyncio.gather(*(cached_json("analytics:test-sf", 30, producer) for _ in range(5)))
        assert results == [{"v": 1}] * 5
        assert calls == 1
        assert cache._inflight == {}
