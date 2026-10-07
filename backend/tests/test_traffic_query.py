"""Traffic page queries: filters, rollup/raw stitching and the /api/traffic routes."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core.cache import cache_delete_prefix
from app.models.proxy_host import ProxyHost
from app.models.traffic_log import TrafficLog
from app.services import traffic_query as tq
from app.services import traffic_rollup_service as rollup
from tests.conftest import TestSessionLocal

NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture(autouse=True)
async def _fresh_cache():
    # Route responses are cached by query string; every test has its own data.
    await cache_delete_prefix("traffic:")
    yield


def _log(host_id, minutes_ago, *, status=200, upstream="10.0.0.5:8080", ip="198.51.100.7",
         uri="/", method="GET", rt=40, country="NZ", bot=False, ua="Mozilla/5.0", streaming=False):
    return TrafficLog(
        id=str(uuid.uuid4()), proxy_host_id=host_id, timestamp=NOW - timedelta(minutes=minutes_ago),
        client_ip=ip, request_method=method, request_uri=uri, status=status, response_time=rt,
        bytes_sent=1000, bytes_received=100, upstream_addr=upstream, country_code=country,
        is_bot=bot, user_agent=ua, is_streaming=streaming,
    )


@pytest.fixture
async def traffic(db_session):
    a = ProxyHost(id=str(uuid.uuid4()), domain_names=["a.example.test"], forward_scheme="http",
                  forward_host="10.0.0.5", forward_port=8080)
    b = ProxyHost(id=str(uuid.uuid4()), domain_names=["b.example.test"], forward_scheme="http",
                  forward_host="10.0.0.6", forward_port=80)
    db_session.add_all([a, b])
    await db_session.flush()
    logs = []
    # Spread over three days, so part lands in rolled-up hours and part in the tail.
    for i in range(60):
        logs.append(_log(a.id, i * 70, status=200 if i % 5 else 502, uri=f"/api/item/{i % 3}", rt=20 + i))
    for i in range(30):
        logs.append(_log(b.id, i * 90, upstream="10.0.0.6:80", ip="203.0.113.9", uri="/login",
                         method="POST", status=404 if i % 3 == 0 else 200, country="AU", bot=i % 2 == 0))
    # A retried request: nginx records both upstreams; the last one answered.
    logs.append(_log(a.id, 5, upstream="10.0.0.9:8080, 10.0.0.5:8081"))
    # A websocket: excluded from latency.
    logs.append(_log(a.id, 6, rt=600_000, streaming=True, status=101))
    db_session.add_all(logs)
    await db_session.commit()
    return {"a": a, "b": b, "logs": logs}


async def _all_raw(db, f, dims, stride=None):
    return await tq.aggregate(db, f, dims, stride=stride, use_rollup=False)


def _key(rows, dims):
    return sorted((tuple(r[d] for d in dims), r["requests"], r["bytes_sent"], r["rt_count"], tuple(r["hist"])) for r in rows)


class TestFilters:
    def test_rejects_bad_ip(self):
        with pytest.raises(tq.FilterError):
            tq.TrafficFilters(client_ip="not-an-ip")

    def test_accepts_cidr_and_normalises(self):
        f = tq.TrafficFilters(client_ip=" 10.0.0.0/8 ", countries=["nz "], methods=["get"])
        assert f.client_ip == "10.0.0.0/8" and f.countries == ["NZ"] and f.methods == ["GET"]
        assert not f.rollup_compatible

    def test_rollup_compatibility(self):
        assert tq.TrafficFilters(host_ids=["x"], backends=["10.0.0.5"], status_classes=[5]).rollup_compatible
        assert not tq.TrafficFilters(path="/x").rollup_compatible

    def test_plan_splits_window(self):
        wm = tq.floor_hour(NOW)
        f = tq.TrafficFilters(start=NOW - timedelta(days=2, minutes=17))
        plan = tq.plan_sources(f, wm)
        rs, re_ = plan.rollup
        assert rs == tq.ceil_hour(f.start) and re_ == wm
        assert plan.raw == [(f.start, rs), (wm, None)]
        # No watermark (job not run yet): everything raw.
        assert tq.plan_sources(f, None).rollup is None
        # Sub-hour chart buckets can't come from hourly rows.
        assert tq.plan_sources(f, wm, stride=timedelta(minutes=5)).rollup is None

    def test_percentile_from_histogram(self):
        hist = [0] * tq.HIST_LEN
        hist[6] = 100  # 50–100 ms
        assert 50 <= tq.percentile(hist, 0.5) <= 100
        assert tq.percentile([0] * tq.HIST_LEN, 0.5) is None


class TestRollupMatchesRaw:
    async def test_aggregates_identical_with_and_without_rollup(self, traffic, db_session):
        res = await rollup.refresh(session_factory=TestSessionLocal)
        assert res["status"] == "ok"
        f = tq.TrafficFilters(start=NOW - timedelta(days=5, minutes=13))
        for dims, stride in (
            (["proxy_host_id", "status"], None),
            (["upstream", "status_class"], None),
            (["upstream_host"], None),
            (["status"], timedelta(hours=3)),
        ):
            names = (["bucket"] if stride else []) + dims
            with_rollup = await tq.aggregate(db_session, f, dims, stride=stride)
            raw = await _all_raw(db_session, f, dims, stride)
            assert _key(with_rollup, names) == _key(raw, names), dims

    async def test_retried_request_counts_for_the_last_upstream(self, traffic, db_session):
        rows = await tq.aggregate(db_session, tq.TrafficFilters(), ["upstream"], use_rollup=False)
        ups = {r["upstream"]: r["requests"] for r in rows}
        assert "10.0.0.5:8081" in ups and "10.0.0.9:8080" not in ups

    async def test_streaming_excluded_from_latency(self, traffic, db_session):
        rows = await tq.aggregate(db_session, tq.TrafficFilters(statuses=[101]), [], use_rollup=False)
        assert rows[0]["requests"] == 1 and rows[0]["rt_count"] == 0

    async def test_rebuild_after_delete_and_purge(self, traffic, db_session):
        await rollup.refresh(session_factory=TestSessionLocal)
        old = traffic["logs"][-35]  # well inside rolled-up hours
        await db_session.delete(await db_session.get(TrafficLog, old.id))
        await db_session.flush()
        await rollup.rebuild_hour_of(db_session, old.timestamp)
        await db_session.commit()
        total, capped = await tq.count_matching(db_session, tq.TrafficFilters())
        assert (total, capped) == (len(traffic["logs"]) - 1, False)

    async def test_refresh_is_idempotent(self, traffic, db_session):
        await rollup.refresh(session_factory=TestSessionLocal)
        await rollup.refresh(session_factory=TestSessionLocal)
        total, _ = await tq.count_matching(db_session, tq.TrafficFilters())
        assert total == len(traffic["logs"])


class TestRawFilters:
    async def test_cidr_prefix_country_bot_slow(self, traffic, db_session):
        async def count(**kw):
            return (await tq.count_matching(db_session, tq.TrafficFilters(**kw)))[0]

        assert await count(client_ip="203.0.113.0/24") == 30
        assert await count(client_ip="203.0.113.9") == 30
        assert await count(path="/api/item", path_mode="prefix") == 60
        assert await count(path="ITEM", path_mode="contains") == 60  # case-insensitive
        assert await count(path="item", path_mode="prefix") == 0
        assert await count(countries=["au"]) == 30
        assert await count(bot=True) == 15
        assert await count(min_response_ms=70) == 10 + 1  # rt 70..79 plus the websocket
        assert await count(methods=["post"], status_classes=[4]) == 10

    async def test_like_wildcards_are_literal(self, traffic, db_session):
        n, _ = await tq.count_matching(db_session, tq.TrafficFilters(path="%"))
        assert n == 0


class TestRoutes:
    async def test_list_filters_and_total(self, client, auth_headers, traffic):
        r = await client.get("/api/traffic/", headers=auth_headers,
                             params={"backend": "10.0.0.6", "status_class": 4, "limit": 5})
        assert r.status_code == 200
        assert r.headers["x-total-count"] == "10" and r.headers["x-total-count-capped"] == "false"
        assert all(row["status"] == 404 and row["host_name"] == "b.example.test" for row in r.json())

    async def test_bad_filter_is_422(self, client, auth_headers, traffic):
        r = await client.get("/api/traffic/", headers=auth_headers, params={"client_ip": "x/y"})
        assert r.status_code == 422
        r = await client.get("/api/traffic/overview", headers=auth_headers, params={"range": "2y"})
        assert r.status_code == 422

    async def test_overview(self, client, auth_headers, traffic):
        r = await client.get("/api/traffic/overview", headers=auth_headers, params={"range": "7d"})
        assert r.status_code == 200
        body = r.json()
        assert body["totals"]["requests"] == len(traffic["logs"])
        assert sum(p["requests"] for p in body["timeseries"]) == len(traffic["logs"])
        assert body["totals"]["errors_5xx"] == 12
        assert body["totals"]["latency"]["p95"] is not None

    async def test_backends_grouping_and_labels(self, client, auth_headers, traffic):
        r = await client.get("/api/traffic/backends", headers=auth_headers, params={"range": "7d"})
        rows = {b["backend"]: b for b in r.json()}
        # Both ports of 10.0.0.5 roll into one machine.
        assert rows["10.0.0.5"]["requests"] == 62
        assert rows["10.0.0.5"]["configured_for"][0]["name"] == "a.example.test"
        r = await client.get("/api/traffic/backends", headers=auth_headers, params={"range": "7d", "group": "hostport"})
        assert {"10.0.0.5:8080", "10.0.0.5:8081", "10.0.0.6:80"} <= {b["backend"] for b in r.json()}

    async def test_top_dimensions(self, client, auth_headers, traffic):
        for dim in ("path", "client_ip", "country", "method", "status", "proxy_host", "backend_host", "user_agent"):
            r = await client.get("/api/traffic/top", headers=auth_headers, params={"dimension": dim, "range": "7d"})
            assert r.status_code == 200, dim
            assert r.json(), dim
        r = await client.get("/api/traffic/top", headers=auth_headers, params={"dimension": "password"})
        assert r.status_code == 422

    async def test_stats_shape(self, client, auth_headers, traffic):
        r = await client.get("/api/traffic/stats", headers=auth_headers, params={"include_top_ips": "false"})
        body = r.json()
        assert body["total_requests"] == len(traffic["logs"])
        assert body["requests_by_method"]["POST"] == 30 and body["top_ips"] == []

    async def test_detail(self, client, auth_headers, traffic):
        log = traffic["logs"][0]
        r = await client.get(f"/api/traffic/{log.id}", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["host_name"] == "a.example.test" and body["backend"]["host"] == "10.0.0.5"

    async def test_deletes_need_admin(self, client, user_auth_headers, auth_headers, traffic):
        log = traffic["logs"][0]
        assert (await client.delete(f"/api/traffic/{log.id}", headers=user_auth_headers)).status_code == 403
        assert (await client.delete("/api/traffic", headers=user_auth_headers)).status_code == 403
        assert (await client.delete(f"/api/traffic/{log.id}", headers=auth_headers)).status_code == 204


class TestNodes:
    async def test_node_breakdown_and_failovers(self, client, auth_headers, traffic):
        a = traffic["a"]
        r = await client.get("/api/traffic/nodes", headers=auth_headers, params={"range": "7d", "host": a.id})
        assert r.status_code == 200
        body = r.json()
        nodes = {n["node"]: n for n in body["nodes"]}
        assert nodes["10.0.0.5:8080"]["requests"] == 61
        assert nodes["10.0.0.5:8081"]["failovers_in"] == 1
        assert nodes["10.0.0.5:8081"]["share"] > 0
        assert body["failovers"]["total"] == 1
        assert body["failovers"]["pairs"] == [{"from": "10.0.0.9:8080", "to": "10.0.0.5:8081", "requests": 1}]
        assert sum(sum(p["values"].values()) for p in body["timeseries"]) == 62

    async def test_failovers_survive_rollup(self, traffic, db_session):
        await rollup.refresh(session_factory=TestSessionLocal)
        rows = await tq.aggregate(db_session, tq.TrafficFilters(start=NOW - timedelta(days=5)), ["upstream"])
        assert sum(r["failovers"] for r in rows) == 1

    async def test_attempt_chain_in_detail(self, client, auth_headers, traffic):
        retried = next(log for log in traffic["logs"] if "," in (log.upstream_addr or ""))
        r = await client.get(f"/api/traffic/{retried.id}", headers=auth_headers)
        chain = r.json()["attempts"]
        assert [c["node"] for c in chain] == ["10.0.0.9:8080", "10.0.0.5:8081"]
        assert chain[-1]["final"] and chain[-1]["status"] == 200 and chain[0]["status"] is None

    async def test_host_report_has_nodes(self, client, auth_headers, traffic):
        r = await client.get(f"/api/reports/hosts/{traffic['a'].id}", headers=auth_headers, params={"period": "7d"})
        assert r.status_code == 200
        assert {n["node"] for n in r.json()["nodes"]["nodes"]} >= {"10.0.0.5:8080", "10.0.0.5:8081"}
