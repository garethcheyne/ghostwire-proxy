---
title: AI Agents (MCP)
excerpt: Let Claude Code or another MCP client configure the proxy
---

> Navigate to **Administration → Settings → AI agents (MCP)**.

Ghostwire Proxy includes a [Model Context Protocol](https://modelcontextprotocol.io) server, so an
AI assistant such as Claude Code can look at and configure your proxy hosts on request.

## Connect Claude Code

1. Create an [API key](./api-keys.md) for the agent. The **Configure hosts** preset gives it
   `read`, `write:proxy-hosts`, `write:upstreams`, `write:certificates`, `write:access` and
   `write:nginx`; choose **Read only** if it should only look.
2. Run this once, with your proxy's address and the key:

```bash
claude mcp add --transport http ghostwire-proxy https://proxy.example.com/api/mcp \
  --header "Authorization: Bearer gwp_your_api_key"
```

Add `--scope user` to make it available in every project. The settings page fills in the address
and, right after you create a key, the key itself.

For Claude Desktop, Cursor or VS Code, add this to the client's MCP configuration:

```json
{
  "mcpServers": {
    "ghostwire-proxy": {
      "type": "http",
      "url": "https://proxy.example.com/api/mcp",
      "headers": { "Authorization": "Bearer gwp_your_api_key" }
    }
  }
}
```

## The endpoint

- `POST /api/mcp` — JSON-RPC 2.0 over Streamable HTTP, stateless (no session is issued).
  Protocol versions 2025-06-18, 2025-03-26 and 2024-11-05.
- Authenticated only with an API key (`Authorization: Bearer gwp_…`); a browser session does not
  work here.
- Requests carrying an `Origin` header from another site are refused.
- It is served by the API and reached through the admin UI's address, like every other `/api` call.

## Tools

| Tool | Scope | What it does |
|------|-------|--------------|
| `ghostwire_proxy_list_proxy_hosts` | read | Every host with domains, backend, SSL, access control, health, load-balancing summary |
| `ghostwire_proxy_get_proxy_host` | read | One host in full (by ID or any of its domains) |
| `ghostwire_proxy_get_proxy_host_config` | read | The nginx config nginx is running for a host |
| `ghostwire_proxy_preview_config` | read | Render a proposed change and diff it against the running config; saves nothing |
| `ghostwire_proxy_list_certificates` | read | Certificates with status and expiry |
| `ghostwire_proxy_list_access_lists` | read | IP access lists |
| `ghostwire_proxy_list_auth_walls` | read | Auth walls |
| `ghostwire_proxy_list_upstreams` | read | A host's balancing method and upstream servers with health |
| `ghostwire_proxy_get_health_summary` | read | Health of every host and upstream server, plus system status |
| `ghostwire_proxy_get_traffic_summary` | read | Request counts, status codes, top hosts and paths |
| `ghostwire_proxy_get_recent_changes` | read | The audit log, including changes made with keys |
| `ghostwire_proxy_create_proxy_host` | write:proxy-hosts | Create a host |
| `ghostwire_proxy_update_proxy_host` | write:proxy-hosts | Change domains, backend, SSL, HSTS, websockets, access list, auth wall, … |
| `ghostwire_proxy_set_proxy_host_enabled` | write:proxy-hosts | Enable or disable a host |
| `ghostwire_proxy_set_load_balancing` | write:proxy-hosts | Balancing method, keepalive, auto-down, or replace the whole upstream list |
| `ghostwire_proxy_add_upstream` | write:upstreams | Add an upstream server (weight, backup, down, max_conns, …) |
| `ghostwire_proxy_update_upstream` | write:upstreams | Change one upstream server |
| `ghostwire_proxy_remove_upstream` | write:upstreams | Remove one upstream server |
| `ghostwire_proxy_request_certificate` | write:certificates | Request a Let's Encrypt certificate |
| `ghostwire_proxy_test_nginx_config` | write:nginx | Run `nginx -t` |
| `ghostwire_proxy_reload_nginx` | write:nginx | Regenerate every host's config and reload; requires `confirm: true` |

### Dry runs

Every tool that changes nginx config accepts `dry_run: true`. It returns the config the change
would produce and a unified diff against the running file, and saves nothing. Real changes go
through the same path as the admin UI: the config is generated, checked with `nginx -t`, and only
saved and reloaded if it passes.

### Deliberately missing

There are no tools to delete hosts, certificates, access lists or users, so a bad prompt cannot do
lasting damage through the agent. Use the admin UI for those.

## Auditing

Each change an agent makes is in the audit log twice: once as the normal entry (for example
`proxy_host_updated`, under the key owner's email) and once as `api_key_used`, naming the key. Ask
the agent for `ghostwire_proxy_get_recent_changes`, or call `GET /api/audit-logs`.
