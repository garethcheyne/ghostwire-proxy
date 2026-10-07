"""The MCP endpoint: JSON-RPC protocol (a port of ghostwire-load's protocol.test.ts) and the
/api/mcp route with real API keys and tools."""
import pytest

from app.core.rate_limiter import limiter
from app.mcp.protocol import LATEST_PROTOCOL_VERSION, RPC, McpTool, ServerInfo, handle_message
from app.models.proxy_host import ProxyHost, UpstreamServer
from app.services import api_key_service

INFO = ServerInfo(name="ghostwire-proxy", title="Ghostwire Proxy", version="1.0.0")


def make_tool(handler=None) -> McpTool:
    async def pong(_args):
        return {"content": [{"type": "text", "text": "pong"}]}
    return McpTool(name="ghostwire_ping", title="Ping", description="Returns pong.",
                   input_schema={"type": "object"}, handler=handler or pong)


async def call(message, tools=None):
    return await handle_message(message, tools=tools if tools is not None else [make_tool()], info=INFO)


class TestProtocol:
    async def test_initialize_answers_with_client_version_when_supported(self):
        r = await call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
        assert r["result"]["protocolVersion"] == "2024-11-05"

    async def test_initialize_falls_back_to_newest(self):
        r = await call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
        assert r["result"]["protocolVersion"] == LATEST_PROTOCOL_VERSION

    async def test_initialize_advertises_tools_only(self):
        r = await call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert r["result"]["capabilities"] == {"tools": {}}

    async def test_notifications_get_no_reply(self):
        assert await call({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
        assert await call({"jsonrpc": "2.0", "method": "notifications/cancelled"}) is None

    async def test_tools_list_hides_handler(self):
        r = await call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        (described,) = r["result"]["tools"]
        assert described["name"] == "ghostwire_ping"
        assert described["inputSchema"] == {"type": "object"}
        assert "handler" not in described

    async def test_tools_call_returns_content(self):
        r = await call({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "ghostwire_ping", "arguments": {}}})
        assert r["result"]["content"][0]["text"] == "pong"

    async def test_thrown_tool_is_a_result_not_protocol_error(self):
        async def boom(_args):
            raise RuntimeError("the database is down")
        r = await call({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "ghostwire_ping"}},
                       [make_tool(boom)])
        assert "error" not in r
        assert r["result"]["isError"] is True
        assert r["result"]["content"][0]["text"] == "the database is down"

    async def test_unknown_tool_names_available(self):
        r = await call({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "ghostwire_nope"}})
        assert r["error"]["code"] == RPC.INVALID_PARAMS
        assert r["error"]["data"]["available"] == ["ghostwire_ping"]

    async def test_rejects_non_jsonrpc(self):
        r = await call({"id": 6, "method": "tools/list"})
        assert r["error"]["code"] == RPC.INVALID_REQUEST

    async def test_rejects_unknown_method(self):
        r = await call({"jsonrpc": "2.0", "id": 7, "method": "resources/list"})
        assert r["error"]["code"] == RPC.METHOD_NOT_FOUND


@pytest.fixture(autouse=True)
def _reset_limits():
    limiter.reset()
    api_key_service.failed_attempts.reset()


async def make_key(db_session, user, scopes):
    _, key = await api_key_service.create_key(db_session, user, "mcp-test", scopes, None)
    await db_session.commit()
    return key


@pytest.fixture
async def host(db_session):
    h = ProxyHost(domain_names=["app.example.com"], forward_scheme="http", forward_host="10.0.0.5", forward_port=8080)
    db_session.add(h)
    await db_session.flush()
    db_session.add(UpstreamServer(proxy_host_id=h.id, host="10.0.0.5", port=8080))
    db_session.add(UpstreamServer(proxy_host_id=h.id, host="10.0.0.6", port=8080))
    await db_session.commit()
    return h


async def rpc(client, key, method, params=None, id_=1, headers=None):
    return await client.post(
        "/api/mcp",
        headers={"Authorization": f"Bearer {key}", **(headers or {})},
        json={"jsonrpc": "2.0", "id": id_, "method": method, **({"params": params} if params is not None else {})},
    )


async def tool_call(client, key, name, arguments):
    r = await rpc(client, key, "tools/call", {"name": name, "arguments": arguments})
    assert r.status_code == 200, r.text
    return r.json()["result"]


class TestEndpoint:
    async def test_requires_api_key(self, client, auth_headers):
        r = await client.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert r.status_code == 401
        # A session token is not an API key.
        r = await client.post("/api/mcp", headers=auth_headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert r.status_code == 401

    async def test_invalid_key_rejected(self, client):
        r = await rpc(client, "gwp_" + "a" * 10 + "_" + "b" * 40, "initialize")
        assert r.status_code == 401

    async def test_initialize_and_list(self, client, db_session, admin_user):
        key = await make_key(db_session, admin_user, ["read"])
        r = await rpc(client, key, "initialize", {"protocolVersion": "2025-06-18"})
        assert r.status_code == 200
        assert r.json()["result"]["serverInfo"]["name"] == "ghostwire-proxy"

        r = await rpc(client, key, "tools/list")
        names = {t["name"] for t in r.json()["result"]["tools"]}
        assert {"ghostwire_proxy_list_proxy_hosts", "ghostwire_proxy_create_proxy_host",
                "ghostwire_proxy_add_upstream", "ghostwire_proxy_set_load_balancing",
                "ghostwire_proxy_request_certificate", "ghostwire_proxy_reload_nginx"} <= names
        assert not any("delete" in n for n in names)

    async def test_notification_is_202(self, client, db_session, admin_user):
        key = await make_key(db_session, admin_user, ["read"])
        r = await client.post("/api/mcp", headers={"Authorization": f"Bearer {key}"},
                              json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        assert r.status_code == 202

    async def test_batch_rejected(self, client, db_session, admin_user):
        key = await make_key(db_session, admin_user, ["read"])
        r = await client.post("/api/mcp", headers={"Authorization": f"Bearer {key}"},
                              json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}])
        assert r.status_code == 400

    async def test_foreign_origin_rejected(self, client, db_session, admin_user):
        key = await make_key(db_session, admin_user, ["read"])
        r = await rpc(client, key, "ping", headers={"Origin": "https://evil.example"})
        assert r.status_code == 403

    async def test_unsupported_protocol_header(self, client, db_session, admin_user):
        key = await make_key(db_session, admin_user, ["read"])
        r = await rpc(client, key, "ping", headers={"MCP-Protocol-Version": "1999-01-01"})
        assert r.status_code == 400

    async def test_get_is_405(self, client):
        assert (await client.get("/api/mcp")).status_code == 405


class TestTools:
    async def test_list_and_get_host_by_domain(self, client, db_session, admin_user, host):
        key = await make_key(db_session, admin_user, ["read"])
        result = await tool_call(client, key, "ghostwire_proxy_list_proxy_hosts", {})
        assert result["structuredContent"]["items"][0]["domain_names"] == ["app.example.com"]

        result = await tool_call(client, key, "ghostwire_proxy_get_proxy_host", {"host": "app.example.com"})
        assert result["structuredContent"]["id"] == host.id
        assert len(result["structuredContent"]["upstream_servers"]) == 2

    async def test_read_key_cannot_mutate(self, client, db_session, admin_user, host):
        key = await make_key(db_session, admin_user, ["read"])
        result = await tool_call(client, key, "ghostwire_proxy_set_proxy_host_enabled",
                                 {"host": "app.example.com", "enabled": False})
        assert result["isError"] is True
        assert "write:proxy-hosts" in result["content"][0]["text"]
        await db_session.refresh(host)
        assert host.enabled is True

    async def test_dry_run_create_renders_config(self, client, db_session, admin_user):
        key = await make_key(db_session, admin_user, ["write:proxy-hosts"])
        result = await tool_call(client, key, "ghostwire_proxy_create_proxy_host", {
            "domain_names": ["new.example.com"], "forward_host": "10.1.1.1", "forward_port": 3000, "dry_run": True,
        })
        assert not result.get("isError"), result
        preview = result["structuredContent"]
        assert "server_name new.example.com;" in preview["config"]
        assert "+server {" in preview["diff"] or "server_name" in preview["diff"]
        # Nothing saved
        listed = await tool_call(client, key, "ghostwire_proxy_list_proxy_hosts", {})
        assert listed["structuredContent"]["items"] == []

    async def test_dry_run_upstream_change_renders_upstream_block(self, client, db_session, admin_user, host):
        key = await make_key(db_session, admin_user, ["write:upstreams"])
        result = await tool_call(client, key, "ghostwire_proxy_add_upstream", {
            "host": "app.example.com", "address": "10.0.0.7", "port": 8080, "backup": True, "dry_run": True,
        })
        assert not result.get("isError"), result
        config = result["structuredContent"]["config"]
        assert "10.0.0.7:8080" in config
        await db_session.refresh(host, ["upstream_servers"])
        assert len(host.upstream_servers) == 2

    async def test_invalid_change_is_reported(self, client, db_session, admin_user, host):
        key = await make_key(db_session, admin_user, ["write:proxy-hosts"])
        result = await tool_call(client, key, "ghostwire_proxy_set_load_balancing",
                                 {"host": host.id, "lb_method": "fastest", "dry_run": True})
        assert result["isError"] is True
        assert "lb_method" in result["content"][0]["text"]

    async def test_unknown_domain(self, client, db_session, admin_user, host):
        key = await make_key(db_session, admin_user, ["read"])
        result = await tool_call(client, key, "ghostwire_proxy_get_proxy_host", {"host": "nope.example.com"})
        assert result["isError"] is True

    async def test_reload_needs_confirm_and_scope(self, client, db_session, admin_user):
        key = await make_key(db_session, admin_user, ["read"])
        result = await tool_call(client, key, "ghostwire_proxy_reload_nginx", {"confirm": True})
        assert result["isError"] is True and "write:nginx" in result["content"][0]["text"]

        key = await make_key(db_session, admin_user, ["write:nginx"])
        result = await tool_call(client, key, "ghostwire_proxy_reload_nginx", {})
        assert result["isError"] is True and "confirm" in result["content"][0]["text"]

    async def test_recent_changes(self, client, db_session, admin_user):
        key = await make_key(db_session, admin_user, ["read"])
        result = await tool_call(client, key, "ghostwire_proxy_get_recent_changes", {"limit": 5})
        assert "items" in result["structuredContent"]
