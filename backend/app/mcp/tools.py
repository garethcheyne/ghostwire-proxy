"""The tools the MCP endpoint exposes: what an agent needs to configure the proxy.

Every tool goes through the REST API in-process (httpx over ASGI, same app) carrying the caller's
own API key, so each call gets exactly the checks, validation, audit log entries and
validate-then-commit nginx apply that the admin UI gets. A tool also checks its scope up front so
the agent gets a clear message instead of a bare 403.

Deleting hosts, certificates, access lists or users is deliberately absent: a bad prompt cannot
do lasting damage through this door. Mutations that change nginx config take `dry_run`, which
renders the proposed config and a diff against what nginx runs now without saving anything.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from app.mcp.protocol import McpTool, ToolError, ToolResult
from app.services.api_key_service import ApiKeyPrincipal

UUID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")

LB_METHODS = ["round_robin", "least_conn", "ip_hash", "hash_uri", "random_two"]


def _result(value: Any, summary: Optional[str] = None) -> ToolResult:
    structured = value if isinstance(value, dict) else {"items": value}
    text = json.dumps(structured, indent=2, default=str)
    if summary:
        text = f"{summary}\n\n{text}"
    return {"content": [{"type": "text", "text": text}], "structuredContent": structured}


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


HOST_REF = {
    "type": "string",
    "description": "The proxy host: its ID, or one of its domain names (e.g. \"app.example.com\").",
}
DRY_RUN = {
    "type": "boolean",
    "default": False,
    "description": "Preview only: return the nginx config this would produce and a diff against the "
                   "running config. Nothing is saved or reloaded.",
}

# Host fields an agent may set on create/update, with their JSON schema.
HOST_FIELDS: dict[str, Any] = {
    "domain_names": {"type": "array", "items": {"type": "string"}, "minItems": 1,
                     "description": "Domains this host answers for, e.g. [\"app.example.com\"]. Wildcards like *.example.com allowed."},
    "forward_scheme": {"type": "string", "enum": ["http", "https"], "description": "Scheme to the backend."},
    "forward_host": {"type": "string", "description": "Backend host name or IP (used when the host has no upstream servers)."},
    "forward_port": {"type": "integer", "minimum": 1, "maximum": 65535, "description": "Backend port."},
    "ssl_enabled": {"type": "boolean", "description": "Serve HTTPS with certificate_id."},
    "ssl_force": {"type": "boolean", "description": "Redirect HTTP to HTTPS."},
    "certificate_id": {"type": ["string", "null"], "description": "Certificate ID (see ghostwire_proxy_list_certificates)."},
    "http2_support": {"type": "boolean", "description": "Enable HTTP/2 on the HTTPS listener."},
    "hsts_enabled": {"type": "boolean", "description": "Send Strict-Transport-Security."},
    "hsts_subdomains": {"type": "boolean", "description": "Add includeSubDomains to HSTS."},
    "websockets_support": {"type": "boolean", "description": "Pass WebSocket upgrades through."},
    "block_exploits": {"type": "boolean", "description": "Block common exploit patterns."},
    "access_list_id": {"type": ["string", "null"], "description": "IP access list ID, or null for none (see ghostwire_proxy_list_access_lists)."},
    "auth_wall_id": {"type": ["string", "null"], "description": "Auth wall ID (login in front of the site), or null for none (see ghostwire_proxy_list_auth_walls)."},
    "cdn_provider": {"type": "string", "enum": ["none", "cloudflare", "imperva", "generic"],
                     "description": "CDN/WAF in front of the host; decides which header gives the real visitor IP."},
    "client_max_body_size": {"type": "string", "description": "Max request body, e.g. \"100m\"."},
    "proxy_read_timeout": {"type": "integer", "minimum": 1, "description": "Seconds to wait for the backend to respond."},
    "traffic_logging_enabled": {"type": "boolean", "description": "Record per-request traffic logs for this host."},
    "enabled": {"type": "boolean", "description": "Whether nginx serves this host."},
}

SERVER_FIELDS: dict[str, Any] = {
    "address": {"type": "string", "description": "Upstream server host name or IP."},
    "port": {"type": "integer", "minimum": 1, "maximum": 65535},
    "weight": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Relative share of traffic (default 1)."},
    "max_fails": {"type": "integer", "minimum": 0, "maximum": 100, "description": "Failures before nginx marks it unavailable (default 3; 0 = never)."},
    "fail_timeout": {"type": "integer", "minimum": 1, "maximum": 3600, "description": "Seconds it stays unavailable (default 30)."},
    "backup": {"type": "boolean", "description": "Only receives traffic when every primary server is down."},
    "down": {"type": "boolean", "description": "Maintenance: kept in the group but sent no traffic."},
    "max_conns": {"type": ["integer", "null"], "minimum": 1, "description": "Cap on simultaneous connections (null = unlimited)."},
    "enabled": {"type": "boolean", "description": "Include this server in the generated config."},
}


def _server_payload(args: dict[str, Any]) -> dict[str, Any]:
    body = {k: v for k, v in args.items() if k in SERVER_FIELDS and k != "address"}
    if "address" in args:
        body["host"] = args["address"]
    return body


class ProxyApi:
    """The REST API, called in-process with the caller's key."""

    def __init__(self, app, authorization: str, client_ip: str | None, user_agent: str | None):
        headers = {"Authorization": authorization, "User-Agent": f"ghostwire-proxy-mcp ({user_agent or 'unknown client'})"}
        if client_ip:
            headers["X-Forwarded-For"] = client_ip
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://ghostwire-proxy-api",
            headers=headers,
            timeout=180.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def call(self, method: str, path: str, *, json_body: Any = None, params: dict | None = None) -> Any:
        response = await self._client.request(method, path, json=json_body, params=params)
        if response.status_code == 204:
            return {"ok": True}
        try:
            body = response.json()
        except ValueError:
            body = {"detail": response.text[:2000]}
        if response.status_code >= 400:
            detail = body.get("detail") if isinstance(body, dict) else body
            if isinstance(detail, list):  # FastAPI validation errors
                detail = "; ".join(
                    f"{'.'.join(str(p) for p in e.get('loc', [])[1:]) or 'body'}: {e.get('msg')}" for e in detail
                )
            raise ToolError(f"{method} {path} failed ({response.status_code}): {detail}")
        return body

    async def all_hosts(self) -> list[dict]:
        hosts: list[dict] = []
        skip = 0
        while True:
            page = await self.call("GET", "/api/proxy-hosts/", params={"skip": skip, "limit": 100})
            hosts.extend(page)
            if len(page) < 100:
                return hosts
            skip += 100

    async def find_host(self, ref: str) -> dict:
        ref = (ref or "").strip()
        if not ref:
            raise ToolError("Give the host's ID or one of its domain names.")
        if UUID_RE.match(ref):
            return await self.call("GET", f"/api/proxy-hosts/{ref}")
        wanted = ref.lower().removeprefix("https://").removeprefix("http://").split("/")[0]
        for host in await self.all_hosts():
            if wanted in [d.lower() for d in host.get("domain_names", [])]:
                return host
        raise ToolError(f'No proxy host has the domain "{wanted}". List them with ghostwire_proxy_list_proxy_hosts.')

    async def preview(self, host_id: str | None, changes: dict) -> dict:
        return await self.call("POST", "/api/config/preview", json_body={"host_id": host_id, "changes": changes})


def _host_summary(h: dict) -> dict:
    servers = h.get("upstream_servers") or []
    return {
        "id": h["id"],
        "domain_names": h.get("domain_names"),
        "forward": f"{h.get('forward_scheme')}://{h.get('forward_host')}:{h.get('forward_port')}",
        "enabled": h.get("enabled"),
        "ssl_enabled": h.get("ssl_enabled"),
        "certificate_id": h.get("certificate_id"),
        "access_list_id": h.get("access_list_id"),
        "auth_wall_id": h.get("auth_wall_id"),
        "websockets_support": h.get("websockets_support"),
        "health_status": h.get("health_status"),
        "lb_method": h.get("lb_method"),
        "upstream_servers": len(servers),
        "locations": len(h.get("locations") or []),
    }


def _server_list(host: dict) -> list[dict]:
    """The host's upstream servers in the shape the full-list replace takes (ids kept)."""
    keep = set(SERVER_FIELDS) - {"address"} | {"id", "host"}
    return [{k: v for k, v in s.items() if k in keep} for s in host.get("upstream_servers") or []]


def build_tools(principal: ApiKeyPrincipal, api: ProxyApi) -> list[McpTool]:
    def guarded(scope: str, fn):
        async def handler(args: dict[str, Any]) -> ToolResult:
            if not principal.allows(scope):
                raise ToolError(
                    f"This API key does not have the '{scope}' scope. Ask an admin to create a key "
                    f"with it under Settings > API keys."
                )
            return await fn(args)
        return handler

    def tool(name: str, title: str, description: str, schema: dict, scope: str, fn, **annotations) -> McpTool:
        return McpTool(
            name=f"ghostwire_proxy_{name}",
            title=title,
            description=f"{description} Requires API key scope: {scope}.",
            input_schema=schema,
            handler=guarded(scope, fn),
            scope=scope,
            annotations=annotations,
        )

    ro = {"readOnlyHint": True, "openWorldHint": False}
    rw = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}

    # ---- read ------------------------------------------------------------------

    async def list_proxy_hosts(args):
        hosts = await api.all_hosts()
        if args.get("search"):
            needle = args["search"].lower()
            hosts = [h for h in hosts if needle in " ".join(h.get("domain_names", [])).lower()
                     or needle in (h.get("forward_host") or "").lower()]
        if args.get("enabled") is not None:
            hosts = [h for h in hosts if h.get("enabled") == args["enabled"]]
        return _result([_host_summary(h) for h in hosts], f"{len(hosts)} proxy host(s).")

    async def get_proxy_host(args):
        return _result(await api.find_host(args["host"]))

    async def get_proxy_host_config(args):
        host = await api.find_host(args["host"])
        return _result(await api.call("GET", f"/api/proxy-hosts/{host['id']}/config"))

    async def preview_config(args):
        host_id = (await api.find_host(args["host"]))["id"] if args.get("host") else None
        return _result(await api.preview(host_id, args.get("changes") or {}))

    async def list_certificates(args):
        return _result(await api.call("GET", "/api/certificates/", params={"limit": 100}))

    async def list_access_lists(args):
        return _result(await api.call("GET", "/api/access-lists/"))

    async def list_auth_walls(args):
        return _result(await api.call("GET", "/api/auth-walls/"))

    async def list_upstreams(args):
        host = await api.find_host(args["host"])
        return _result({
            "host_id": host["id"],
            "domain_names": host.get("domain_names"),
            "lb_method": host.get("lb_method"),
            "upstream_keepalive": host.get("upstream_keepalive"),
            "servers": host.get("upstream_servers") or [],
        })

    async def health_summary(args):
        hosts = await api.all_hosts()
        report = []
        for h in hosts:
            report.append({
                "id": h["id"],
                "domain_names": h.get("domain_names"),
                "enabled": h.get("enabled"),
                "health_status": h.get("health_status"),
                "health_checked_at": h.get("health_checked_at"),
                "health_error": h.get("health_error"),
                "upstreams": [
                    {"id": s.get("id"), "address": f"{s.get('host')}:{s.get('port')}",
                     "status": s.get("last_status"), "latency_ms": s.get("last_latency_ms"),
                     "error": s.get("last_error"), "down": s.get("down"), "auto_down": s.get("auto_down")}
                    for s in h.get("upstream_servers") or []
                ],
            })
        down = [r for r in report if r["health_status"] == "down"]
        system = None
        try:
            system = await api.call("GET", "/api/system/status")
        except ToolError:
            pass
        return _result({"hosts": report, "hosts_down": len(down), "system": system},
                       f"{len(report)} host(s), {len(down)} down.")

    async def traffic_summary(args):
        return _result(await api.call("GET", "/api/traffic/stats", params={"days": args.get("days", 7)}))

    async def recent_changes(args):
        params = {"limit": args.get("limit", 25)}
        if args.get("action"):
            params["action"] = args["action"]
        return _result(await api.call("GET", "/api/audit-logs/", params=params))

    # ---- proxy hosts -------------------------------------------------------------

    async def create_proxy_host(args):
        body = {k: v for k, v in args.items() if k in HOST_FIELDS}
        if args.get("dry_run"):
            return _result(await api.preview(None, body), "Dry run: nothing was saved.")
        created = await api.call("POST", "/api/proxy-hosts/", json_body=body)
        return _result(created, "Created; nginx config validated and reloaded.")

    async def update_proxy_host(args):
        host = await api.find_host(args["host"])
        body = {k: v for k, v in args.items() if k in HOST_FIELDS}
        if not body:
            raise ToolError("Nothing to change: pass at least one field.")
        if args.get("dry_run"):
            return _result(await api.preview(host["id"], body), "Dry run: nothing was saved.")
        updated = await api.call("PUT", f"/api/proxy-hosts/{host['id']}", json_body=body)
        return _result(updated, "Updated; nginx config validated and reloaded.")

    async def set_enabled(args):
        host = await api.find_host(args["host"])
        enabled = bool(args["enabled"])
        if args.get("dry_run"):
            return _result(await api.preview(host["id"], {"enabled": enabled}), "Dry run: nothing was saved.")
        action = "enable" if enabled else "disable"
        return _result(await api.call("POST", f"/api/proxy-hosts/{host['id']}/{action}"), f"Host {action}d.")

    async def set_load_balancing(args):
        host = await api.find_host(args["host"])
        body = {k: args[k] for k in ("lb_method", "upstream_keepalive", "lb_auto_down") if k in args}
        if "servers" in args:
            body["upstream_servers"] = [_server_payload(s) | ({"id": s["id"]} if s.get("id") else {}) for s in args["servers"]]
        if not body:
            raise ToolError("Nothing to change: pass lb_method, upstream_keepalive, lb_auto_down or servers.")
        if args.get("dry_run"):
            return _result(await api.preview(host["id"], body), "Dry run: nothing was saved.")
        updated = await api.call("PUT", f"/api/proxy-hosts/{host['id']}", json_body=body)
        missing = [k for k in body if k != "upstream_servers" and k not in updated]
        note = f" Note: this server version ignored {', '.join(missing)}." if missing else ""
        return _result(_host_summary(updated) | {"servers": updated.get("upstream_servers")},
                       f"Load balancing updated; nginx config validated and reloaded.{note}")

    # ---- upstream servers --------------------------------------------------------

    async def add_upstream(args):
        host = await api.find_host(args["host"])
        server = _server_payload(args)
        if args.get("dry_run"):
            servers = _server_list(host) + [server]
            return _result(await api.preview(host["id"], {"upstream_servers": servers}), "Dry run: nothing was saved.")
        created = await api.call("POST", f"/api/proxy-hosts/{host['id']}/upstreams", json_body=server)
        ignored = [k for k in server if k not in created]
        note = f" Note: this server version ignored {', '.join(ignored)}." if ignored else ""
        return _result(created, f"Upstream server added; nginx config validated and reloaded.{note}")

    async def update_upstream(args):
        host = await api.find_host(args["host"])
        changes = _server_payload(args)
        if not changes:
            raise ToolError("Nothing to change.")
        if args.get("dry_run"):
            servers = _server_list(host)
            if not any(s["id"] == args["server_id"] for s in servers):
                raise ToolError("No upstream server with that id on this host.")
            servers = [s | changes if s["id"] == args["server_id"] else s for s in servers]
            return _result(await api.preview(host["id"], {"upstream_servers": servers}), "Dry run: nothing was saved.")
        updated = await api.call("PATCH", f"/api/proxy-hosts/{host['id']}/upstreams/{args['server_id']}", json_body=changes)
        return _result(updated, "Upstream server updated; nginx config validated and reloaded.")

    async def remove_upstream(args):
        host = await api.find_host(args["host"])
        if args.get("dry_run"):
            servers = [s for s in _server_list(host) if s["id"] != args["server_id"]]
            return _result(await api.preview(host["id"], {"upstream_servers": servers}), "Dry run: nothing was saved.")
        await api.call("DELETE", f"/api/proxy-hosts/{host['id']}/upstreams/{args['server_id']}")
        return _result({"removed": args["server_id"]}, "Upstream server removed; nginx config validated and reloaded.")

    # ---- certificates -------------------------------------------------------------

    async def request_certificate(args):
        body = {"name": args.get("name") or args["domain_names"][0], "domain_names": args["domain_names"], "email": args["email"]}
        cert = await api.call("POST", "/api/certificates/letsencrypt", json_body=body)
        return _result(cert, "Certificate requested from Let's Encrypt. Attach it to a host with "
                             "ghostwire_proxy_update_proxy_host (certificate_id, ssl_enabled).")

    # ---- nginx ---------------------------------------------------------------------

    async def test_nginx(args):
        return _result(await api.call("POST", "/api/config/test"))

    async def reload_nginx(args):
        if args.get("confirm") is not True:
            raise ToolError("Reloading regenerates every host's config and reloads nginx. Call again with confirm: true.")
        return _result(await api.call("POST", "/api/config/reload"))

    server_props = {k: v for k, v in SERVER_FIELDS.items()}

    return [
        tool("list_proxy_hosts", "List proxy hosts",
             "Every proxy host with its domains, backend, SSL, access control, health and load-balancing summary.",
             _schema({"search": {"type": "string", "description": "Filter by domain or backend host substring."},
                      "enabled": {"type": "boolean", "description": "Only enabled (true) or disabled (false) hosts."}}),
             "read", list_proxy_hosts, **ro),
        tool("get_proxy_host", "Get a proxy host", "Full settings of one proxy host, including upstream servers and locations.",
             _schema({"host": HOST_REF}, ["host"]), "read", get_proxy_host, **ro),
        tool("get_proxy_host_config", "Get a host's nginx config",
             "The nginx config file for a host exactly as nginx is running it.",
             _schema({"host": HOST_REF}, ["host"]), "read", get_proxy_host_config, **ro),
        tool("preview_config", "Preview a config change",
             "Render the nginx config a host would get with the given changes (or a new host, if host is omitted) "
             "and diff it against the running config. Saves nothing.",
             _schema({"host": HOST_REF, "changes": {"type": "object", "description": "Proxy-host fields to change (same names as update_proxy_host; upstream_servers replaces the server list)."}}),
             "read", preview_config, **ro),
        tool("list_certificates", "List certificates", "TLS certificates with their domains, status and expiry.",
             _schema({}), "read", list_certificates, **ro),
        tool("list_access_lists", "List access lists", "IP access lists (allow/deny rules) that can be attached to hosts.",
             _schema({}), "read", list_access_lists, **ro),
        tool("list_auth_walls", "List auth walls", "Auth walls (login pages) that can be put in front of hosts.",
             _schema({}), "read", list_auth_walls, **ro),
        tool("list_upstreams", "List a host's upstream servers",
             "The load-balancing method and upstream servers of a host, with each server's health.",
             _schema({"host": HOST_REF}, ["host"]), "read", list_upstreams, **ro),
        tool("get_health_summary", "Health summary",
             "Health of every host and upstream server, plus system status.",
             _schema({}), "read", health_summary, **ro),
        tool("get_traffic_summary", "Traffic summary", "Request counts, status codes, top hosts and paths over recent days.",
             _schema({"days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 7}}),
             "read", traffic_summary, **ro),
        tool("get_recent_changes", "Recent changes", "The audit log, newest first: who changed what, including changes made with API keys.",
             _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 25},
                      "action": {"type": "string", "description": "Filter by action prefix, e.g. \"proxy_host\" or \"api_key\"."}}),
             "read", recent_changes, **ro),

        tool("create_proxy_host", "Create a proxy host",
             "Create a proxy host. The config is checked with nginx -t before anything is saved; on failure nothing changes.",
             _schema({**HOST_FIELDS, "dry_run": DRY_RUN}, ["domain_names", "forward_host", "forward_port"]),
             "write:proxy-hosts", create_proxy_host, **rw),
        tool("update_proxy_host", "Update a proxy host",
             "Change a proxy host's settings (only the fields given). Checked with nginx -t first; on failure nothing changes.",
             _schema({"host": HOST_REF, **HOST_FIELDS, "dry_run": DRY_RUN}, ["host"]),
             "write:proxy-hosts", update_proxy_host, **rw, idempotentHint=True),
        tool("set_proxy_host_enabled", "Enable or disable a proxy host", "Turn a host on or off in nginx.",
             _schema({"host": HOST_REF, "enabled": {"type": "boolean"}, "dry_run": DRY_RUN}, ["host", "enabled"]),
             "write:proxy-hosts", set_enabled, **rw, idempotentHint=True),
        tool("set_load_balancing", "Set load balancing",
             "Set a host's balancing method and, optionally, replace its whole upstream server list "
             "(servers with an id are updated, without one added, missing ones removed; [] means a single backend again).",
             _schema({
                 "host": HOST_REF,
                 "lb_method": {"type": "string", "enum": LB_METHODS, "description": "round_robin (default), least_conn, ip_hash (sticky by client IP), hash_uri, random_two."},
                 "upstream_keepalive": {"type": "integer", "minimum": 0, "maximum": 1024, "description": "Idle keepalive connections per worker (0 = off)."},
                 "lb_auto_down": {"type": "boolean", "description": "Take servers the health check finds down out of the group."},
                 "servers": {"type": "array", "items": _schema({"id": {"type": "string"}, **server_props}, ["address", "port"])},
                 "dry_run": DRY_RUN,
             }, ["host"]),
             "write:proxy-hosts", set_load_balancing, **rw, idempotentHint=True),

        tool("add_upstream", "Add an upstream server", "Add a backend server to a host's load-balanced group.",
             _schema({"host": HOST_REF, **server_props, "dry_run": DRY_RUN}, ["host", "address", "port"]),
             "write:upstreams", add_upstream, **rw),
        tool("update_upstream", "Update an upstream server",
             "Change one upstream server (weight, backup, down for maintenance, max_conns, ...).",
             _schema({"host": HOST_REF, "server_id": {"type": "string"}, **server_props, "dry_run": DRY_RUN}, ["host", "server_id"]),
             "write:upstreams", update_upstream, **rw, idempotentHint=True),
        tool("remove_upstream", "Remove an upstream server", "Remove one backend server from a host's group.",
             _schema({"host": HOST_REF, "server_id": {"type": "string"}, "dry_run": DRY_RUN}, ["host", "server_id"]),
             "write:upstreams", remove_upstream, readOnlyHint=False, destructiveHint=True, openWorldHint=False),

        tool("request_certificate", "Request a certificate",
             "Request a Let's Encrypt certificate (HTTP-01). The domains must already point at this proxy.",
             _schema({"domain_names": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                      "email": {"type": "string", "description": "Contact email for Let's Encrypt."},
                      "name": {"type": "string", "description": "Display name (defaults to the first domain)."}},
                     ["domain_names", "email"]),
             "write:certificates", request_certificate, readOnlyHint=False, destructiveHint=False, openWorldHint=True),

        tool("test_nginx_config", "Test the nginx config", "Run nginx -t on the configuration nginx has now.",
             _schema({}), "write:nginx", test_nginx, readOnlyHint=True, openWorldHint=False),
        tool("reload_nginx", "Regenerate and reload nginx",
             "Regenerate every host's config from the database, run nginx -t and reload; all or nothing. "
             "Normal saves already do this, so only use it to recover from drift.",
             _schema({"confirm": {"type": "boolean", "description": "Must be true."}}, ["confirm"]),
             "write:nginx", reload_nginx, **rw),
    ]
