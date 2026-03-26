---
title: Proxy Hosts
excerpt: Create and manage reverse proxy entries with SSL, load balancing, and advanced routing
---

Proxy Hosts are the core of Ghostwire Proxy. Each proxy host maps one or more domain names to an upstream service, handling SSL termination, load balancing, and security at the edge.

![Proxy Hosts](../_img/proxy-hosts.png)

## Creating a Proxy Host

To add a new proxy host, click **Add Proxy Host** and configure the following sections.

### Domain Names

Enter one or more domain names that this proxy host should respond to. All domains share the same upstream configuration.

### Forwarding

| Field | Description |
|-------|-------------|
| **Scheme** | `http` or `https` — the protocol used to connect to your upstream |
| **Forward Host** | IP address or hostname of your upstream service |
| **Forward Port** | Port number on the upstream service |

### SSL / TLS

| Option | Description |
|--------|-------------|
| **SSL Certificate** | Select a certificate from your certificate library |
| **Force SSL** | Redirect all HTTP requests to HTTPS |
| **HTTP/2** | Enable HTTP/2 protocol support |
| **HSTS** | Send Strict-Transport-Security header |
| **HSTS Subdomains** | Include subdomains in the HSTS policy |

### Advanced Options

| Option | Description |
|--------|-------------|
| **WebSockets** | Enable WebSocket protocol upgrade support |
| **Block Exploits** | Enable basic XSS and path traversal blocking |
| **Client Max Body Size** | Maximum upload size (e.g., `50m` for 50 MB) |
| **Custom Nginx Config** | Raw nginx directives injected into the server block |

## Load Balancing

Proxy hosts support multiple upstream servers for load balancing. Add additional upstream entries with:

- **Host** and **Port** for each backend server
- **Weight** — relative traffic distribution
- **Health checks** — automatic removal of unhealthy backends

## Locations

Locations allow path-based routing within a single proxy host. Each location can have its own upstream and configuration.

| Field | Description |
|-------|-------------|
| **Path** | URI path to match (e.g., `/api`) |
| **Match Type** | `prefix`, `exact`, `regex`, or `case-insensitive regex` |
| **Priority** | Order of evaluation (higher priority routes match first) |
| **Upstream** | Different forward host/port per location |
| **Timeouts** | Custom connect, send, and read timeouts per location |

## Traffic Control

| Option | Description |
|--------|-------------|
| **Traffic Logging** | Enable/disable per-request logging for this host |
| **Response Caching** | Cache upstream responses with configurable validity and bypass rules |
| **Rate Limiting** | Per-host request throttling (see [Rate Limiting](../security/rate-limits.md)) |

## Security Bindings

Each proxy host can be associated with security features:

- **[Access List](../security/access-lists.md)** — IP whitelist or blacklist
- **[Auth Wall](../security/auth-walls.md)** — Login gate protecting the service
- **[WAF Rules](../security/waf.md)** — Scoped per-host or global
- **[GeoIP Rules](../security/geoip.md)** — Country-level blocking

## Enabling and Disabling

Use the toggle switch to enable or disable a proxy host without deleting its configuration. Disabled hosts stop receiving traffic immediately after nginx is reloaded.
