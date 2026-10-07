"""Load balancing: upstream block generation, LB rules, the API and per-server health."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.proxy_host import ProxyHost, UpstreamServer
from app.schemas.proxy_host import UpstreamServerCreate, ProxyHostUpdate
from app.services import health_service
from app.services.load_balancing import (
    check_lb_rules,
    format_server_address,
    normalize_upstream_host,
    validate_health_check_path,
)
from app.services.openresty_service import (
    generate_server_block,
    generate_upstream_block,
    generate_upstream_connection_map,
    generate_upstream_location_directives,
)

HOST_ID = "11111111-2222-3333-4444-555555555555"
UP = "upstream_11111111_2222_3333_4444_555555555555"


def srv(port, host="10.0.0.5", **kw):
    base = dict(host=host, port=port, weight=1, max_fails=3, fail_timeout=30,
                backup=False, down=False, max_conns=None, enabled=True, auto_down=False)
    base.update(kw)
    return SimpleNamespace(**base)


def lb_host(servers, **kw):
    base = dict(
        id=HOST_ID, lb_method="round_robin", upstream_keepalive=32, lb_auto_down=False,
        websockets_support=False, upstream_servers=servers,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def full_host(servers, **kw):
    """A host with every attribute generate_server_block reads."""
    base = dict(
        id=HOST_ID, domain_names=["shop.example.com"], forward_scheme="http",
        forward_host="10.0.0.5", forward_port=8050, ssl_enabled=False, http2_support=True,
        hsts_enabled=False, hsts_subdomains=False, websockets_support=False, block_exploits=False,
        access_list_id=None, access_list=None, auth_wall_id=None, auth_wall=None,
        advanced_config=None, server_advanced_config=None, client_max_body_size="100m",
        proxy_buffering=True, proxy_buffer_size="4k", proxy_buffers="8 4k",
        proxy_connect_timeout=60, proxy_send_timeout=60, proxy_read_timeout=60,
        cache_enabled=False, cache_valid=None, cache_bypass=None, rate_limit_enabled=False,
        rate_limit_requests=100, rate_limit_period="1s", rate_limit_burst=50,
        custom_error_pages=None, honeypot_enabled=False, traffic_logging_enabled=False,
        cdn_provider="none", locations=[], upstream_servers=servers,
        lb_method="round_robin", upstream_keepalive=32, lb_auto_down=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


FOUR = [srv(8050), srv(8051), srv(8052), srv(8053)]


class TestUpstreamBlock:
    def test_no_servers_no_block(self):
        assert generate_upstream_block(lb_host([])) == ""

    def test_only_disabled_servers_no_block(self):
        assert generate_upstream_block(lb_host([srv(8050, enabled=False)])) == ""

    def test_round_robin_snapshot(self):
        assert generate_upstream_block(lb_host(FOUR)) == "\n".join([
            f"upstream {UP} {{",
            "    # Load balancing: Round robin",
            f"    zone {UP} 64k;",
            "    server 10.0.0.5:8050;",
            "    server 10.0.0.5:8051;",
            "    server 10.0.0.5:8052;",
            "    server 10.0.0.5:8053;",
            "    keepalive 32;",
            "}",
        ])

    def test_least_conn_snapshot(self):
        assert generate_upstream_block(lb_host(FOUR, lb_method="least_conn")) == "\n".join([
            f"upstream {UP} {{",
            "    # Load balancing: Least connections",
            f"    zone {UP} 64k;",
            "    least_conn;",
            "    server 10.0.0.5:8050;",
            "    server 10.0.0.5:8051;",
            "    server 10.0.0.5:8052;",
            "    server 10.0.0.5:8053;",
            "    keepalive 32;",
            "}",
        ])

    @pytest.mark.parametrize("method,directive", [
        ("ip_hash", "    ip_hash;"),
        ("hash_uri", "    hash $request_uri consistent;"),
        ("random_two", "    random two least_conn;"),
    ])
    def test_method_directive_before_servers_and_keepalive(self, method, directive):
        lines = generate_upstream_block(lb_host(FOUR, lb_method=method)).split("\n")
        assert lines[3] == directive
        assert lines.index(directive) < lines.index("    keepalive 32;")

    def test_unknown_method_falls_back_to_round_robin(self):
        block = generate_upstream_block(lb_host(FOUR, lb_method="nonsense"))
        assert "Round robin" in block and "least_conn" not in block

    def test_server_params(self):
        block = generate_upstream_block(lb_host([
            srv(8050, weight=3, max_fails=5, fail_timeout=10, max_conns=200),
            srv(8051, backup=True),
            srv(8052, down=True),
        ], lb_method="least_conn"))
        assert "    server 10.0.0.5:8050 weight=3 max_fails=5 fail_timeout=10s max_conns=200;" in block
        assert "    server 10.0.0.5:8051 backup;" in block
        assert "    server 10.0.0.5:8052 down;" in block

    def test_backup_dropped_for_methods_nginx_rejects_it_with(self):
        block = generate_upstream_block(lb_host([srv(8050), srv(8051, backup=True)], lb_method="ip_hash"))
        assert "backup" not in block

    def test_down_allowed_with_ip_hash(self):
        block = generate_upstream_block(lb_host([srv(8050), srv(8051, down=True)], lb_method="ip_hash"))
        assert "    server 10.0.0.5:8051 down;" in block

    def test_auto_down_only_when_enabled(self):
        servers = [srv(8050), srv(8051, auto_down=True)]
        assert "down" not in generate_upstream_block(lb_host(servers))
        block = generate_upstream_block(lb_host(servers, lb_auto_down=True))
        assert "    server 10.0.0.5:8051 down;  # health check: down" in block

    def test_keepalive_custom_and_off(self):
        assert "keepalive 64;" in generate_upstream_block(lb_host(FOUR, upstream_keepalive=64))
        assert "keepalive" not in generate_upstream_block(lb_host(FOUR, upstream_keepalive=0))

    def test_ipv6_bracketed(self):
        assert "server [fd00::5]:8050;" in generate_upstream_block(lb_host([srv(8050, host="fd00::5")]))


class TestLocationDirectives:
    def test_single_server_keepalive_no_retries(self):
        lines = generate_upstream_location_directives(lb_host([srv(8050)]), indent="")
        assert 'proxy_set_header Connection "";' in lines
        assert not any("proxy_next_upstream" in line for line in lines)

    def test_multi_server_retries_capped(self):
        lines = generate_upstream_location_directives(lb_host(FOUR), indent="")
        assert "proxy_next_upstream error timeout http_502 http_503 http_504;" in lines
        assert "proxy_next_upstream_tries 3;" in lines
        two = generate_upstream_location_directives(lb_host(FOUR[:2]), indent="")
        assert "proxy_next_upstream_tries 2;" in two

    def test_websockets_use_keepalive_safe_map(self):
        host = lb_host(FOUR, websockets_support=True)
        lines = generate_upstream_location_directives(host, indent="")
        assert not any("Connection" in line for line in lines)  # set by the WebSocket block instead
        assert generate_upstream_connection_map(host) == "\n".join([
            "map $http_upgrade $gw_conn_11111111222233334444555555555555 {",
            "    default upgrade;",
            "    ''      \"\";",
            "}",
        ])

    def test_no_map_without_keepalive(self):
        assert generate_upstream_connection_map(lb_host(FOUR, websockets_support=True, upstream_keepalive=0)) == ""


class TestServerBlock:
    def test_single_backend_unchanged(self):
        conf = generate_server_block(full_host([]))
        assert "upstream " not in conf
        assert "proxy_pass http://10.0.0.5:8050;" in conf
        assert "proxy_next_upstream" not in conf
        assert 'proxy_set_header Connection "";' not in conf

    def test_load_balanced_server_block(self):
        conf = generate_server_block(full_host(FOUR, lb_method="least_conn"))
        assert conf.index(f"upstream {UP} {{") < conf.index("server {")
        assert f"proxy_pass http://{UP};" in conf
        assert "proxy_next_upstream_tries 3;" in conf
        assert 'proxy_set_header Connection "";' in conf

    def test_load_balanced_with_websockets(self):
        conf = generate_server_block(full_host(FOUR, websockets_support=True))
        assert "map $http_upgrade $gw_conn_" in conf
        assert "proxy_set_header Connection $gw_conn_" in conf
        assert "$connection_upgrade;" not in conf

    def test_all_disabled_falls_back_to_forward_host(self):
        conf = generate_server_block(full_host([srv(8050, enabled=False)]))
        assert "upstream " not in conf
        assert "proxy_pass http://10.0.0.5:8050;" in conf


class TestRules:
    def test_empty_is_single_backend(self):
        assert check_lb_rules("least_conn", []) == ([], [])

    def test_needs_a_primary(self):
        errors, _ = check_lb_rules("round_robin", [srv(8050, backup=True)])
        assert any("isn't a backup" in e for e in errors)
        errors, _ = check_lb_rules("round_robin", [srv(8050, enabled=False)])
        assert errors

    @pytest.mark.parametrize("method", ["ip_hash", "hash_uri", "random_two"])
    def test_backup_rejected_with_hash_methods(self, method):
        errors, _ = check_lb_rules(method, [srv(8050), srv(8051, backup=True)])
        assert any("backup" in e for e in errors)

    @pytest.mark.parametrize("method", ["round_robin", "least_conn"])
    def test_backup_allowed(self, method):
        assert check_lb_rules(method, [srv(8050), srv(8051, backup=True)])[0] == []

    def test_duplicates(self):
        errors, _ = check_lb_rules("round_robin", [srv(8050), srv(8050)])
        assert any("more than once" in e for e in errors)

    def test_all_down_warns(self):
        errors, warnings = check_lb_rules("round_robin", [srv(8050, down=True), srv(8051, down=True)])
        assert not errors and any("502" in w for w in warnings)

    def test_unknown_method(self):
        assert check_lb_rules("fastest", [srv(8050)])[0]

    def test_dicts_accepted(self):
        assert check_lb_rules("ip_hash", [{"host": "a", "port": 1, "backup": True}, {"host": "b", "port": 1}])[0]


class TestFieldValidation:
    @pytest.mark.parametrize("value", ["10.0.0.5", "backend", "node-1.internal", "fd00::5", "[fd00::5]", "my_service"])
    def test_good_hosts(self, value):
        normalize_upstream_host(value)

    @pytest.mark.parametrize("value", ["", "10.0.0.5:80", "http://x", "a b", "x;y", "x}", "a/b"])
    def test_bad_hosts(self, value):
        with pytest.raises(ValueError):
            normalize_upstream_host(value)

    def test_format_address(self):
        assert format_server_address("fd00::5", 80) == "[fd00::5]:80"
        assert format_server_address("10.0.0.1", 80) == "10.0.0.1:80"

    @pytest.mark.parametrize("field,value", [("weight", 0), ("weight", 101), ("max_conns", 0), ("port", 70000), ("fail_timeout", 0)])
    def test_server_ranges(self, field, value):
        with pytest.raises(ValidationError):
            UpstreamServerCreate(**{"host": "10.0.0.5", "port": 8050, field: value})

    @pytest.mark.parametrize("path", ["/healthz", "/", "/status?full=1"])
    def test_good_paths(self, path):
        assert validate_health_check_path(path) == path

    @pytest.mark.parametrize("path", ["healthz", "//evil.example/", "/a b", "/x#y", "http://evil/"])
    def test_bad_paths(self, path):
        with pytest.raises(ValueError):
            validate_health_check_path(path)

    def test_update_rejects_bad_method(self):
        with pytest.raises(ValidationError):
            ProxyHostUpdate(lb_method="fastest")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest.fixture
def nginx_ok():
    """Config generation and reload pass without touching nginx or the disk."""
    with patch("app.api.routes.proxy_hosts.generate_all_configs", new=AsyncMock(return_value=[])), \
         patch("app.api.routes.proxy_hosts.backup_configs"), \
         patch("app.api.routes.proxy_hosts.test_nginx_config", return_value=(True, "ok")), \
         patch("app.api.routes.proxy_hosts.reload_nginx", return_value=(True, "ok")), \
         patch("app.api.routes.proxy_hosts.cache_delete_prefix", new=AsyncMock()):
        yield


def host_payload(**kw):
    data = {"domain_names": ["shop.example.com"], "forward_host": "10.0.0.5", "forward_port": 8050}
    data.update(kw)
    return data


class TestApi:
    async def test_create_load_balanced(self, client, auth_headers, nginx_ok):
        res = await client.post("/api/proxy-hosts/", headers=auth_headers, json=host_payload(
            lb_method="least_conn", cdn_provider="cloudflare",
            upstream_servers=[{"host": "10.0.0.5", "port": p} for p in range(8050, 8054)],
        ))
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["lb_method"] == "least_conn"
        # Used to be dropped on create
        assert body["cdn_provider"] == "cloudflare"
        assert [s["port"] for s in body["upstream_servers"]] == [8050, 8051, 8052, 8053]
        assert body["upstream_servers"][0]["last_status"] == "unknown"

    async def test_create_rejects_ip_hash_with_backup(self, client, auth_headers, nginx_ok):
        res = await client.post("/api/proxy-hosts/", headers=auth_headers, json=host_payload(
            lb_method="ip_hash",
            upstream_servers=[{"host": "10.0.0.5", "port": 8050}, {"host": "10.0.0.5", "port": 8051, "backup": True}],
        ))
        assert res.status_code == 422
        assert "backup" in res.json()["detail"]

    async def test_create_rejects_config_injection(self, client, auth_headers, nginx_ok):
        res = await client.post("/api/proxy-hosts/", headers=auth_headers, json=host_payload(
            upstream_servers=[{"host": "10.0.0.5; include /etc/passwd", "port": 8050}],
        ))
        assert res.status_code == 422

    async def test_update_replaces_servers_and_keeps_health(self, client, auth_headers, nginx_ok, db_session):
        res = await client.post("/api/proxy-hosts/", headers=auth_headers, json=host_payload(
            upstream_servers=[{"host": "10.0.0.5", "port": 8050}, {"host": "10.0.0.5", "port": 8051}],
        ))
        host = res.json()
        keep = host["upstream_servers"][0]
        await db_session.execute(
            UpstreamServer.__table__.update().where(UpstreamServer.id == keep["id"]).values(last_status="up", last_latency_ms=12)
        )
        await db_session.commit()

        res = await client.put(f"/api/proxy-hosts/{host['id']}", headers=auth_headers, json={
            "lb_method": "least_conn",
            "upstream_servers": [
                {"id": keep["id"], "host": "10.0.0.5", "port": 8050, "weight": 2},
                {"host": "10.0.0.5", "port": 8052, "backup": True},
            ],
        })
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["lb_method"] == "least_conn"
        ports = {s["port"]: s for s in body["upstream_servers"]}
        assert set(ports) == {8050, 8052}
        assert ports[8050]["id"] == keep["id"] and ports[8050]["weight"] == 2
        assert ports[8050]["last_status"] == "up" and ports[8050]["last_latency_ms"] == 12
        assert ports[8052]["backup"] is True

    async def test_update_to_single_backend(self, client, auth_headers, nginx_ok):
        res = await client.post("/api/proxy-hosts/", headers=auth_headers, json=host_payload(
            upstream_servers=[{"host": "10.0.0.5", "port": 8050}],
        ))
        hid = res.json()["id"]
        res = await client.put(f"/api/proxy-hosts/{hid}", headers=auth_headers, json={"upstream_servers": []})
        assert res.status_code == 200 and res.json()["upstream_servers"] == []

    async def test_method_change_checked_against_saved_servers(self, client, auth_headers, nginx_ok):
        res = await client.post("/api/proxy-hosts/", headers=auth_headers, json=host_payload(
            upstream_servers=[{"host": "10.0.0.5", "port": 8050}, {"host": "10.0.0.5", "port": 8051, "backup": True}],
        ))
        hid = res.json()["id"]
        res = await client.put(f"/api/proxy-hosts/{hid}", headers=auth_headers, json={"lb_method": "hash_uri"})
        assert res.status_code == 422

    async def test_upstream_crud(self, client, auth_headers, nginx_ok):
        hid = (await client.post("/api/proxy-hosts/", headers=auth_headers, json=host_payload())).json()["id"]
        a = await client.post(f"/api/proxy-hosts/{hid}/upstreams", headers=auth_headers, json={"host": "10.0.0.5", "port": 8050})
        assert a.status_code == 201, a.text
        b = await client.post(f"/api/proxy-hosts/{hid}/upstreams", headers=auth_headers, json={"host": "10.0.0.5", "port": 8051})
        assert b.status_code == 201
        dup = await client.post(f"/api/proxy-hosts/{hid}/upstreams", headers=auth_headers, json={"host": "10.0.0.5", "port": 8051})
        assert dup.status_code == 422

        patched = await client.patch(f"/api/proxy-hosts/{hid}/upstreams/{b.json()['id']}", headers=auth_headers,
                                     json={"down": True, "max_conns": 50})
        assert patched.status_code == 200, patched.text
        assert patched.json()["down"] is True and patched.json()["max_conns"] == 50

        # Removing the only primary while a backup remains is refused
        await client.put(f"/api/proxy-hosts/{hid}/upstreams/{b.json()['id']}", headers=auth_headers, json={"backup": True, "down": False})
        res = await client.delete(f"/api/proxy-hosts/{hid}/upstreams/{a.json()['id']}", headers=auth_headers)
        assert res.status_code == 422

        listed = await client.get(f"/api/proxy-hosts/{hid}/upstreams", headers=auth_headers)
        assert len(listed.json()) == 2

    async def test_upstreams_require_admin(self, client, user_auth_headers, auth_headers, nginx_ok):
        hid = (await client.post("/api/proxy-hosts/", headers=auth_headers, json=host_payload())).json()["id"]
        res = await client.post(f"/api/proxy-hosts/{hid}/upstreams", headers=user_auth_headers, json={"host": "10.0.0.5", "port": 8050})
        assert res.status_code == 403

    async def test_preview(self, client, auth_headers):
        res = await client.post("/api/proxy-hosts/upstream-preview", headers=auth_headers, json={
            "lb_method": "least_conn", "websockets_support": False,
            "servers": [{"host": "10.0.0.5", "port": p} for p in range(8050, 8054)],
        })
        assert res.status_code == 200, res.text
        body = res.json()
        assert "least_conn;" in body["upstream_block"]
        assert "upstream upstream_new_host {" in body["upstream_block"]
        assert "proxy_next_upstream_tries 3;" in body["location_directives"]
        assert body["errors"] == []

    async def test_preview_reports_rule_errors(self, client, auth_headers):
        res = await client.post("/api/proxy-hosts/upstream-preview", headers=auth_headers, json={
            "lb_method": "ip_hash", "host_id": "x; evil",
            "servers": [{"host": "10.0.0.5", "port": 8050}, {"host": "10.0.0.5", "port": 8051, "backup": True}],
        })
        body = res.json()
        assert body["errors"] and "evil" not in body["upstream_block"]


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

async def _make_host(db_session, ports, **kw):
    host = ProxyHost(id=str(uuid.uuid4()), domain_names=["lb.example.com"], forward_host="10.0.0.5",
                     forward_port=ports[0], **kw)
    host.upstream_servers = [UpstreamServer(host="10.0.0.5", port=p) for p in ports]
    db_session.add(host)
    await db_session.commit()
    result = await db_session.execute(
        select(ProxyHost).options(selectinload(ProxyHost.upstream_servers)).where(ProxyHost.id == host.id)
    )
    return result.scalar_one()


class TestHealth:
    @pytest.fixture(autouse=True)
    def _reset(self):
        health_service._server_failures.clear()
        health_service._consecutive_failures.clear()

    async def test_per_server_status_and_host_aggregate(self, db_session):
        host = await _make_host(db_session, [8050, 8051])

        async def fake_probe(scheme, host, port, check_type, path, timeout):
            return (True, None, 7) if port == 8050 else (False, "connection refused", None)

        with patch.object(health_service, "probe_server", side_effect=fake_probe), \
             patch("app.services.push_service.push_service.notify_host_down", new=AsyncMock()), \
             patch("app.services.alert_service.dispatch_alert", new=AsyncMock()):
            await health_service.run_health_checks(db_session)

        await db_session.refresh(host, attribute_names=["upstream_servers", "health_status"])
        by_port = {s.port: s for s in host.upstream_servers}
        assert by_port[8050].last_status == "up" and by_port[8050].last_latency_ms == 7
        assert by_port[8051].last_status == "down" and by_port[8051].last_error == "connection refused"
        assert host.health_status == "up"  # one backend answering keeps the host up

    async def test_probe_args_use_host_settings(self, db_session):
        host = await _make_host(db_session, [8050], health_check_type="tcp", health_check_path="/healthz", health_check_timeout=2)
        args = health_service._probe_args(host, host.upstream_servers[0])
        assert args == {"scheme": "http", "host": "10.0.0.5", "port": 8050, "check_type": "tcp", "path": "/healthz", "timeout": 2.0}

    def test_auto_down_keeps_one_server(self):
        host = SimpleNamespace(lb_auto_down=True)
        a = SimpleNamespace(last_status="down", auto_down=False, down=False)
        b = SimpleNamespace(last_status="down", auto_down=False, down=False)
        assert health_service._update_auto_down(host, [a, b]) is True
        assert [a.auto_down, b.auto_down].count(True) == 1

    def test_auto_down_recovers(self):
        host = SimpleNamespace(lb_auto_down=True)
        a = SimpleNamespace(last_status="up", auto_down=True, down=False)
        b = SimpleNamespace(last_status="up", auto_down=False, down=False)
        assert health_service._update_auto_down(host, [a, b]) is True and a.auto_down is False

    def test_auto_down_off_changes_nothing(self):
        host = SimpleNamespace(lb_auto_down=False)
        a = SimpleNamespace(last_status="down", auto_down=False, down=False)
        assert health_service._update_auto_down(host, [a, SimpleNamespace(last_status="up", auto_down=False, down=False)]) is False
        assert a.auto_down is False

    async def test_probe_server_http_never_follows_redirects(self):
        import httpx

        seen = []

        def handler(request):
            seen.append(str(request.url))
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data"})

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient

        def client_factory(**kw):
            assert kw["follow_redirects"] is False and kw["trust_env"] is False
            return real_client(transport=transport, **kw)

        with patch.object(health_service.httpx, "AsyncClient", side_effect=client_factory):
            ok, error, latency = await health_service.probe_server("http", "10.0.0.5", 8050, "http", "/healthz?x=1", 2)
        assert ok is True and error is None
        assert seen == ["http://10.0.0.5:8050/healthz?x=1"]

    async def test_probe_server_5xx_is_down(self):
        import httpx
        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(lambda r: httpx.Response(503))
        with patch.object(health_service.httpx, "AsyncClient", side_effect=lambda **kw: real_client(transport=transport, **kw)):
            ok, error, _ = await health_service.probe_server("http", "10.0.0.5", 8050, "http", "/", 2)
        assert ok is False and error == "HTTP 503"

    async def test_probe_server_tcp_refused(self):
        ok, error, latency = await health_service.probe_server("http", "127.0.0.1", 1, "tcp", "/", 1)
        assert ok is False and latency is None


async def test_probe_url_has_no_empty_query():
    import httpx
    seen = []
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda r: (seen.append(str(r.url)), httpx.Response(200))[1])
    with patch.object(health_service.httpx, "AsyncClient", side_effect=lambda **kw: real_client(transport=transport, **kw)):
        await health_service.probe_server("http", "10.0.0.5", 8050, "http", "/healthz", 2)
    assert seen == ["http://10.0.0.5:8050/healthz"]


# ---------------------------------------------------------------------------
# Recording which backend served a request
# ---------------------------------------------------------------------------

from app.services.upstream_log import match_upstream_server, parse_upstream, split_host_port  # noqa: E402


class TestUpstreamLogParsing:
    def test_single_backend(self):
        r = parse_upstream("10.0.0.5:8050", "200", "0.012")
        assert r.final_addr == "10.0.0.5:8050" and r.final.status == 200 and r.final_time_ms == 12
        assert r.count == 1 and r.failover is False

    def test_failover_lists(self):
        r = parse_upstream("10.0.0.5:8050, 10.0.0.5:8051", "502, 200", "0.004, 0.120")
        assert [a.addr for a in r.attempts] == ["10.0.0.5:8050", "10.0.0.5:8051"]
        assert [a.status for a in r.attempts] == [502, 200]
        assert [a.time_ms for a in r.attempts] == [4, 120]
        assert r.final_addr == "10.0.0.5:8051" and r.final_time_ms == 120
        assert r.count == 2 and r.failover is True

    def test_internal_redirect_group_separator(self):
        r = parse_upstream("10.0.0.5:8050, 10.0.0.5:8051 : 10.0.0.9:80", "502, 504 : 200", "0.001, 5.000 : 0.050")
        assert r.count == 3 and r.final_addr == "10.0.0.9:80" and r.final.status == 200

    def test_dash_values_and_ipv6(self):
        r = parse_upstream("[fd00::5]:8050, [fd00::5]:8051", "-, 200", "-, 0.2")
        assert r.attempts[0].status is None and r.attempts[0].time_ms is None
        assert r.final_addr == "[fd00::5]:8051" and r.final_time_ms == 200

    def test_no_live_upstreams(self):
        r = parse_upstream("upstream_abc", "502", "0.000")
        assert r.final_addr == "upstream_abc" and r.final.status == 502

    def test_empty(self):
        r = parse_upstream(None, None, None)
        assert r.count == 0 and r.final is None and r.failover is False

    def test_short_lists(self):
        r = parse_upstream("a:1, b:2", "502", None)
        assert r.attempts[1].status is None and r.attempts[1].time_ms is None

    def test_split_host_port(self):
        assert split_host_port("10.0.0.5:8050") == ("10.0.0.5", 8050)
        assert split_host_port("[FD00::5]:80") == ("fd00::5", 80)
        assert split_host_port("upstream_x") == ("upstream_x", None)

    async def test_match_by_ip_and_port(self):
        servers = [SimpleNamespace(id="a", host="10.0.0.5", port=8050), SimpleNamespace(id="b", host="10.0.0.5", port=8051)]
        assert await match_upstream_server("10.0.0.5:8051", servers) == "b"
        assert await match_upstream_server("10.0.0.6:8051", servers) is None
        assert await match_upstream_server("upstream_x", servers) is None
        assert await match_upstream_server("[fd00::5]:80", [SimpleNamespace(id="c", host="fd00::5", port=80)]) == "c"

    async def test_match_hostname_by_resolving(self):
        servers = [SimpleNamespace(id="n", host="localhost", port=8050)]
        assert await match_upstream_server("127.0.0.1:8050", servers) == "n"


class TestTrafficLogEndpoint:
    async def _post(self, client, **kw):
        body = {"timestamp": 1790000000, "client_ip": "203.0.113.9", "method": "GET", "uri": "/",
                "host": "lb.example.com", "status_code": 200, "response_time_ms": 125.0}
        body.update(kw)
        return await client.post("/api/internal/traffic/log", json=body,
                                 headers={"X-Internal-Auth": __import__("app.api.routes.internal", fromlist=["x"]).INTERNAL_AUTH_TOKEN})

    async def test_records_failover_and_server(self, client, db_session):
        from app.models.traffic_log import TrafficLog
        host = await _make_host(db_session, [8050, 8051])
        res = await self._post(client, upstream_addr="10.0.0.5:8050, 10.0.0.5:8051",
                               upstream_status="502, 200", upstream_response_time="0.004, 0.120")
        assert res.json() == {"status": "logged"}
        row = (await db_session.execute(select(TrafficLog))).scalar_one()
        by_port = {s.port: s.id for s in host.upstream_servers}
        assert row.upstream_server_id == by_port[8051]
        assert row.upstream_status == 200 and row.upstream_response_time == 120
        assert row.upstream_attempts == 2 and row.upstream_failover is True
        assert row.upstream_attempt_log == [
            {"addr": "10.0.0.5:8050", "status": 502, "ms": 4},
            {"addr": "10.0.0.5:8051", "status": 200, "ms": 120},
        ]

    async def test_single_backend_host_unchanged(self, client, db_session):
        from app.models.traffic_log import TrafficLog
        db_session.add(ProxyHost(id=str(uuid.uuid4()), domain_names=["lb.example.com"], forward_host="10.0.0.5", forward_port=3000))
        await db_session.commit()
        await self._post(client, upstream_addr="10.0.0.5:3000", upstream_status="200", upstream_response_time="0.050")
        row = (await db_session.execute(select(TrafficLog))).scalar_one()
        assert row.upstream_addr == "10.0.0.5:3000" and row.upstream_response_time == 50
        assert row.upstream_server_id is None and row.upstream_attempts == 1 and row.upstream_failover is False
        assert row.upstream_attempt_log is None


class TestUpdateValidation:
    @pytest.mark.parametrize("payload", [
        {"forward_port": 70000},
        {"forward_port": 0},
        {"forward_scheme": "ftp"},
        {"domain_names": []},
        {"domain_names": ["bad domain"]},
        {"forward_host": "10.0.0.5; include /etc/passwd"},
        {"forward_host": "http://10.0.0.5"},
        {"upstream_keepalive": 5000},
        {"health_check_path": "//evil.example/"},
        {"upstream_servers": [{"host": "10.0.0.5", "port": 8050, "weight": 0}]},
    ])
    def test_schema_rejects(self, payload):
        with pytest.raises(ValidationError):
            ProxyHostUpdate(**payload)

    def test_partial_update_still_allowed(self):
        assert ProxyHostUpdate(enabled=False).model_dump(exclude_unset=True) == {"enabled": False}

    async def test_api_rejects_bad_port_before_nginx(self, client, auth_headers, nginx_ok):
        hid = (await client.post("/api/proxy-hosts/", headers=auth_headers, json=host_payload())).json()["id"]
        with patch("app.api.routes.proxy_hosts.test_nginx_config") as nginx_t:
            res = await client.put(f"/api/proxy-hosts/{hid}", headers=auth_headers, json={"forward_port": 70000})
        assert res.status_code == 422
        nginx_t.assert_not_called()
