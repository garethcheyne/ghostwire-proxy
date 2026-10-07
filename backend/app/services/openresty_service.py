"""
OpenResty/Nginx configuration generation service.
Generates nginx server blocks from ProxyHost database records.
Supports multiple locations, caching, rate limiting, and custom headers.
"""
import glob
import ipaddress
import logging
import os
import shutil
import socket
import subprocess
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import decrypt_data
from app.models.proxy_host import ProxyHost, ProxyLocation
from app.models.certificate import Certificate
from app.models.auth_wall import AuthWall
from app.models.access_list import AccessList
from app.services.load_balancing import (
    BACKUP_METHODS,
    DEFAULT_FAIL_TIMEOUT,
    DEFAULT_KEEPALIVE,
    DEFAULT_MAX_FAILS,
    DEFAULT_WEIGHT,
    LB_METHOD_LABELS,
    LB_METHODS,
    MAX_NEXT_UPSTREAM_TRIES,
    format_server_address,
)


# Which request header carries the true client IP for each front-facing service.
# nginx only honours these from addresses listed in set_real_ip_from (see
# proxy/nginx.conf), so a header from anyone else is ignored rather than trusted.
CDN_REAL_IP_HEADERS = {
    "cloudflare": "CF-Connecting-IP",
    "imperva": "Incap-Client-IP",
    # A plain reverse proxy / load balancer in front of us.
    "generic": "X-Forwarded-For",
    # Reached directly. X-Forwarded-For is still the right header for a LAN load
    # balancer, and is only honoured from the trusted ranges anyway.
    "none": "X-Forwarded-For",
}


# Populated by generate_all_configs() before rendering, from
# trusted_proxy_service. Module-level because generate_server_block() is sync
# and can't await a lookup mid-render.
_TRUSTED_PROXY_RANGES: dict[str, list[str]] = {}


def set_trusted_proxy_ranges(ranges: dict) -> None:
    global _TRUSTED_PROXY_RANGES
    _TRUSTED_PROXY_RANGES = ranges or {}


def _safe_id(id_str: str) -> str:
    """Convert UUID to nginx-safe identifier"""
    return id_str.replace('-', '_')


# The Ghostwire welcome page, as the body of a `location` block. Served by the
# default site and, when chosen, to visitors an IP access list blocks.
_WELCOME_PAGE = [
    "        default_type text/html;",
    "        return 200 '<!DOCTYPE html>",
    "<html lang=\"en\">",
    "<head>",
    "    <meta charset=\"UTF-8\">",
    "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
    "    <title>Ghostwire Proxy</title>",
    "    <style>",
    "        * { margin: 0; padding: 0; box-sizing: border-box; }",
    "        body { font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;",
    "               background: #0f172a; color: #e2e8f0; display: flex; align-items: center;",
    "               justify-content: center; min-height: 100vh; }",
    "        .card { text-align: center; max-width: 480px; padding: 3rem; }",
    "        .icon { font-size: 4rem; margin-bottom: 1.5rem; }",
    "        h1 { font-size: 1.75rem; font-weight: 700; color: #22d3ee; margin-bottom: 0.5rem; }",
    "        p { color: #94a3b8; line-height: 1.6; }",
    "        .badge { display: inline-block; margin-top: 1.5rem; padding: 0.5rem 1rem;",
    "                 background: rgba(34,211,238,0.1); color: #22d3ee; border-radius: 9999px;",
    "                 font-size: 0.875rem; border: 1px solid rgba(34,211,238,0.2); }",
    "    </style>",
    "</head>",
    "<body>",
    "    <div class=\"card\">",
    "        <div class=\"icon\">&#128737;</div>",
    "        <h1>Ghostwire Proxy</h1>",
    "        <p>This server is powered by Ghostwire Proxy. If you are seeing this page, no site has been configured for this hostname yet.</p>",
    "        <div class=\"badge\">Reverse Proxy Active</div>",
    "    </div>",
    "</body>",
    "</html>';",
]


def _generate_access_list_rules(host: ProxyHost, indent: str = "    ") -> list[str]:
    """nginx allow/deny lines for the host's IP access list.

    nginx checks them in order and the first match wins, then the last line
    settles everyone not listed: denied for a whitelist, allowed for a
    blacklist. At server level they cover every location, custom ones included.
    """
    if not host.access_list_id or not host.access_list:
        return []

    acl = host.access_list
    lines = [f"{indent}# IP access list: {acl.id} ({acl.mode})"]
    for entry in acl.entries or []:
        # Re-parse rather than trust the stored text: it goes straight into the config.
        try:
            network = ipaddress.ip_network(entry.ip_or_cidr.strip(), strict=False)
        except ValueError:
            logger.warning(f"Access list {acl.id}: skipping invalid entry {entry.ip_or_cidr!r}")
            continue
        verb = "allow" if entry.action == "allow" else "deny"
        lines.append(f"{indent}{verb} {network};")
    lines.append(f"{indent}{'deny' if acl.mode == 'whitelist' else 'allow'} all;")
    lines.append("")
    lines.extend(_generate_access_list_blocked_response(host, indent))
    return lines


def _generate_access_list_blocked_response(host: ProxyHost, indent: str = "    ") -> list[str]:
    """Send blocked visitors what the list asks for instead of nginx's bare 403.

    `deny` always answers 403, so the list's choice hangs off error_page 403.
    The Lua block pages (WAF, geo) write their own response before exiting, so
    error_page never replaces them; only the access list's deny lands here.
    """
    acl = host.access_list
    behavior = getattr(acl, "blocked_behavior", None) or "403"
    redirect_url = getattr(acl, "blocked_redirect_url", None)

    if behavior == "403" or (behavior == "redirect" and not redirect_url):
        return []
    if "403" in {str(code) for code in (getattr(host, "custom_error_pages", None) or {})}:
        logger.warning(f"Host {host.id}: its custom 403 page takes precedence over access list {acl.id}'s blocked response")
        return []

    lines = [
        f"{indent}# Blocked by the IP access list: {behavior}",
        f"{indent}error_page 403 = @ip_access_blocked;",
        f"{indent}location @ip_access_blocked {{",
        # Without this the list's own `deny all` would refuse this location too,
        # and nginx would fall back to its plain 403.
        f"{indent}    allow all;",
    ]
    if behavior == "redirect":
        # 302, not 301: a list changes, and browsers keep a 301 for good
        lines.append(f"{indent}    return 302 {redirect_url};")
    elif behavior == "404":
        lines.append(f"{indent}    return 404;")
    elif behavior == "444":
        lines.append(f"{indent}    return 444;")
    else:
        lines.extend(_WELCOME_PAGE)
    lines.append(f"{indent}}}")
    lines.append("")
    return lines


def active_upstream_servers(host) -> list:
    """The host's enabled upstream servers, in config order."""
    return [s for s in (getattr(host, "upstream_servers", None) or []) if getattr(s, "enabled", True)]


def uses_upstream_group(host) -> bool:
    """True when "/" proxies to an upstream group rather than forward_host:port.

    A host with no enabled upstream servers keeps the plain single-backend
    config, byte for byte.
    """
    return bool(active_upstream_servers(host))


def upstream_name(host) -> str:
    return f"upstream_{_safe_id(host.id)}"


def _lb_method(host) -> str:
    method = getattr(host, "lb_method", None)
    return method if isinstance(method, str) and method in LB_METHODS else "round_robin"


def _upstream_keepalive(host) -> int:
    value = getattr(host, "upstream_keepalive", None)
    return value if isinstance(value, int) and value >= 0 else DEFAULT_KEEPALIVE


def _connection_map_var(host) -> str:
    # Kept short: nginx's default variables_hash_bucket_size (64) rejects long
    # variable names, so the id goes in without its dashes.
    return f"$gw_conn_{str(host.id).replace('-', '')}"


def _upstream_server_line(host, server, method: str) -> str:
    params = []
    weight = getattr(server, "weight", DEFAULT_WEIGHT)
    if isinstance(weight, int) and weight != DEFAULT_WEIGHT:
        params.append(f"weight={weight}")
    max_fails = getattr(server, "max_fails", DEFAULT_MAX_FAILS)
    if isinstance(max_fails, int) and max_fails != DEFAULT_MAX_FAILS:
        params.append(f"max_fails={max_fails}")
    fail_timeout = getattr(server, "fail_timeout", DEFAULT_FAIL_TIMEOUT)
    if isinstance(fail_timeout, int) and fail_timeout != DEFAULT_FAIL_TIMEOUT:
        params.append(f"fail_timeout={fail_timeout}s")
    max_conns = getattr(server, "max_conns", None)
    if isinstance(max_conns, int) and max_conns > 0:
        params.append(f"max_conns={max_conns}")
    # Validation refuses backup with hash/ip_hash/random; never let a stale row
    # render a config nginx would reject.
    if getattr(server, "backup", False) is True and method in BACKUP_METHODS:
        params.append("backup")
    manual_down = getattr(server, "down", False) is True
    auto_down = getattr(host, "lb_auto_down", False) is True and getattr(server, "auto_down", False) is True
    if manual_down or auto_down:
        params.append("down")

    address = format_server_address(str(server.host), server.port)
    line = f"    server {address}"
    if params:
        line += " " + " ".join(params)
    line += ";"
    if auto_down and not manual_down:
        line += "  # health check: down"
    return line


def generate_upstream_block(host: ProxyHost) -> str:
    """The upstream group for a load-balanced host ("" for a single backend).

    Order matters to nginx: the balancing method has to come before
    `keepalive`. The shared `zone` makes least_conn, random and max_conns count
    connections across all workers instead of per worker.
    """
    servers = active_upstream_servers(host)
    if not servers:
        return ""

    name = upstream_name(host)
    method = _lb_method(host)
    lines = [f"upstream {name} {{"]
    lines.append(f"    # Load balancing: {LB_METHOD_LABELS[method]}")
    lines.append(f"    zone {name} 64k;")
    directive = LB_METHODS[method]
    if directive:
        lines.append(f"    {directive}")
    for server in servers:
        lines.append(_upstream_server_line(host, server, method))
    keepalive = _upstream_keepalive(host)
    if keepalive > 0:
        lines.append(f"    keepalive {keepalive};")
    lines.append("}")
    return "\n".join(lines)


def generate_upstream_connection_map(host) -> str:
    """Per-host Connection header map for a keepalive upstream with WebSockets.

    The global $connection_upgrade map sends `close` for ordinary requests,
    which makes nginx drop every upstream keepalive connection. This one sends
    an empty Connection header instead (so the connection is reused) and still
    upgrades WebSocket requests.
    """
    if not uses_upstream_group(host) or _upstream_keepalive(host) <= 0:
        return ""
    if not getattr(host, "websockets_support", False):
        return ""
    return "\n".join([
        f"map $http_upgrade {_connection_map_var(host)} {{",
        "    default upgrade;",
        "    ''      \"\";",
        "}",
    ])


def generate_upstream_location_directives(host, indent: str = "    ") -> list[str]:
    """Directives the default location needs when it proxies to an upstream group."""
    servers = active_upstream_servers(host)
    if not servers:
        return []
    lines = []
    if _upstream_keepalive(host) > 0 and not getattr(host, "websockets_support", False):
        lines.append(f"{indent}# Reuse upstream connections (keepalive)")
        lines.append(f'{indent}proxy_set_header Connection "";')
    if len(servers) > 1:
        tries = min(len(servers), MAX_NEXT_UPSTREAM_TRIES)
        lines.append(f"{indent}# Try the next server when one fails (non-idempotent requests are not retried)")
        lines.append(f"{indent}proxy_next_upstream error timeout http_502 http_503 http_504;")
        lines.append(f"{indent}proxy_next_upstream_tries {tries};")
    return lines


def _rate_unit(period) -> str:
    """nginx takes r/s or r/m. The UI stores "1s" / "1m" ("100r/1s" fails nginx -t)."""
    unit = str(period or "s").strip().lower().lstrip("1")
    if unit in ("s", "sec", "second"):
        return "s"
    if unit in ("m", "min", "minute"):
        return "m"
    raise ValueError(f"Unsupported rate limit period: {period!r} (use 1s or 1m)")


def _generate_rate_limit_zone(host: ProxyHost) -> str:
    """Generate rate limit zone definition if host or any location has rate limiting enabled"""
    # Check if host has rate limiting enabled
    needs_rate_limit = host.rate_limit_enabled

    # Also check if any location has rate limiting enabled
    if not needs_rate_limit and host.locations:
        for loc in host.locations:
            if loc.enabled and loc.rate_limit_enabled:
                needs_rate_limit = True
                break

    if not needs_rate_limit:
        return ""

    zone_name = f"ratelimit_{_safe_id(host.id)}"
    rate = f"{int(host.rate_limit_requests)}r/{_rate_unit(host.rate_limit_period)}"
    return f"limit_req_zone $binary_remote_addr zone={zone_name}:10m rate={rate};"


def _generate_cache_path(host: ProxyHost) -> str:
    """Generate cache path definition if host or any location has caching enabled"""
    # Check if host has caching enabled
    needs_cache = host.cache_enabled

    # Also check if any location has caching enabled
    if not needs_cache and host.locations:
        for loc in host.locations:
            if loc.enabled and loc.cache_enabled:
                needs_cache = True
                break

    if not needs_cache:
        return ""

    zone_name = f"cache_{_safe_id(host.id)}"
    cache_path = f"/var/cache/nginx/{_safe_id(host.id)}"
    return f"proxy_cache_path {cache_path} levels=1:2 keys_zone={zone_name}:10m max_size=1g inactive=60m;"


def _generate_location_directive(location: ProxyLocation) -> str:
    """Generate nginx location directive based on match type"""
    path = location.path
    match_type = location.match_type

    if match_type == "exact":
        return f"= {path}"
    elif match_type == "regex":
        return f"~ {path}"
    elif match_type == "regex_case_insensitive":
        return f"~* {path}"
    else:  # prefix (default)
        return path


def _generate_access_phase(host: ProxyHost, indent: str = "        ") -> list[str]:
    """The Lua access phase for a proxied location: auth wall, then WAF (incl. honeypot).

    Every location that proxies to a backend must carry this: nginx does not
    inherit access_by_lua into a location from a sibling, so a custom location
    without it would skip the auth wall and the WAF. The auth portal's own
    locations (/__auth/, /api/auth-portal/) and the ACME challenge are the only
    ones left without it. IP access lists and host-level limit_req sit at
    server level and are inherited by every location.
    """
    if host.auth_wall_id and host.block_exploits:
        return [
            f"{indent}access_by_lua_block {{",
            f"{indent}    require('auth_wall').access()",
            f"{indent}    require('waf').access()",
            f"{indent}}}",
        ]
    if host.auth_wall_id:
        return [f"{indent}access_by_lua_block {{ require('auth_wall').access() }}"]
    if host.block_exploits:
        return [f"{indent}access_by_lua_block {{ require('waf').access() }}"]
    return []


def _generate_location_block(
    location: ProxyLocation,
    host: ProxyHost,
    indent: str = "    "
) -> list[str]:
    """Generate a single location block"""
    lines = []
    loc_directive = _generate_location_directive(location)
    backend = f"{location.forward_host}:{location.forward_port}"

    lines.append(f"{indent}location {loc_directive} {{")

    # Auth wall + WAF: same as the default location
    access_phase = _generate_access_phase(host, indent + "    ")
    if access_phase:
        lines.extend(access_phase)
        lines.append("")

    # Rate limiting
    if location.rate_limit_enabled:
        zone_name = f"ratelimit_{_safe_id(host.id)}"
        lines.append(f"{indent}    limit_req zone={zone_name} burst={location.rate_limit_burst} nodelay;")
        lines.append("")

    # Caching
    if location.cache_enabled:
        zone_name = f"cache_{_safe_id(host.id)}"
        lines.append(f"{indent}    proxy_cache {zone_name};")
        if location.cache_valid:
            lines.append(f"{indent}    proxy_cache_valid {location.cache_valid};")
        if location.cache_bypass:
            lines.append(f"{indent}    proxy_cache_bypass {location.cache_bypass};")
        lines.append("")

    # Custom headers (add_header)
    if location.custom_headers:
        for header, value in location.custom_headers.items():
            lines.append(f'{indent}    add_header {header} "{value}";')
        lines.append("")

    # Hide headers from upstream
    if location.hide_headers:
        for header in location.hide_headers:
            lines.append(f"{indent}    proxy_hide_header {header};")
        lines.append("")

    # Proxy pass
    lines.append(f"{indent}    proxy_pass {location.forward_scheme}://{backend};")
    lines.append(f"{indent}    proxy_http_version 1.1;")

    # Proxy headers (can be overridden)
    default_headers = {
        "Host": "$host",
        "X-Real-IP": "$remote_addr",
        "X-Forwarded-For": "$proxy_add_x_forwarded_for",
        "X-Forwarded-Proto": "$scheme",
        "X-Forwarded-Host": "$host",
        "X-Forwarded-Port": "$server_port",
    }

    # Override with custom proxy headers
    if location.proxy_headers:
        default_headers.update(location.proxy_headers)

    for header, value in default_headers.items():
        lines.append(f"{indent}    proxy_set_header {header} {value};")

    # WebSocket support
    if location.websockets_support:
        lines.append("")
        lines.append(f"{indent}    # WebSocket support")
        lines.append(f"{indent}    proxy_set_header Upgrade $http_upgrade;")
        lines.append(f"{indent}    proxy_set_header Connection $connection_upgrade;")

    # Timeouts
    lines.append("")
    lines.append(f"{indent}    proxy_connect_timeout {location.proxy_connect_timeout}s;")
    lines.append(f"{indent}    proxy_send_timeout {location.proxy_send_timeout}s;")
    lines.append(f"{indent}    proxy_read_timeout {location.proxy_read_timeout}s;")

    # Advanced config for this location
    if location.advanced_config:
        lines.append("")
        lines.append(f"{indent}    # Location advanced config")
        for line in location.advanced_config.strip().split("\n"):
            lines.append(f"{indent}    {line}")

    lines.append(f"{indent}}}")
    return lines


def _generate_default_location(
    host: ProxyHost,
    backend: str,
    indent: str = "    "
) -> list[str]:
    """Generate the default (/) location block from host settings"""
    lines = []

    # Rate limiting for default location
    if host.rate_limit_enabled:
        zone_name = f"ratelimit_{_safe_id(host.id)}"
        lines.append(f"{indent}limit_req zone={zone_name} burst={host.rate_limit_burst} nodelay;")
        lines.append("")

    # Caching for default location
    if host.cache_enabled:
        zone_name = f"cache_{_safe_id(host.id)}"
        lines.append(f"{indent}proxy_cache {zone_name};")
        if host.cache_valid:
            lines.append(f"{indent}proxy_cache_valid {host.cache_valid};")
        if host.cache_bypass:
            lines.append(f"{indent}proxy_cache_bypass {host.cache_bypass};")
        lines.append("")

    lines.append(f"{indent}location / {{")

    # Auth wall + WAF (the same access phase every proxied location gets)
    lines.extend(_generate_access_phase(host, indent + "    "))

    # Proxy pass
    scheme = host.forward_scheme
    lines.append(f"{indent}    proxy_pass {scheme}://{backend};")
    lines.append(f"{indent}    proxy_http_version 1.1;")

    # Standard proxy headers
    lines.append(f"{indent}    proxy_set_header Host $host;")
    lines.append(f"{indent}    proxy_set_header X-Real-IP $remote_addr;")
    lines.append(f"{indent}    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;")
    lines.append(f"{indent}    proxy_set_header X-Forwarded-Proto $scheme;")
    lines.append(f"{indent}    proxy_set_header X-Forwarded-Host $host;")
    lines.append(f"{indent}    proxy_set_header X-Forwarded-Port $server_port;")

    # WebSocket support
    if host.websockets_support:
        lines.append("")
        lines.append(f"{indent}    # WebSocket support")
        lines.append(f"{indent}    proxy_set_header Upgrade $http_upgrade;")
        if generate_upstream_connection_map(host):
            # Keepalive-safe variant: empty Connection for ordinary requests
            lines.append(f"{indent}    proxy_set_header Connection {_connection_map_var(host)};")
        else:
            lines.append(f"{indent}    proxy_set_header Connection $connection_upgrade;")

    # Load balancing
    lb_lines = generate_upstream_location_directives(host, indent + "    ")
    if lb_lines:
        lines.append("")
        lines.extend(lb_lines)

    # Timeouts
    lines.append("")
    lines.append(f"{indent}    proxy_connect_timeout {host.proxy_connect_timeout}s;")
    lines.append(f"{indent}    proxy_send_timeout {host.proxy_send_timeout}s;")
    lines.append(f"{indent}    proxy_read_timeout {host.proxy_read_timeout}s;")

    # Advanced config for default location
    if host.advanced_config:
        lines.append("")
        lines.append(f"{indent}    # Advanced config")
        for line in host.advanced_config.strip().split("\n"):
            lines.append(f"{indent}    {line}")

    lines.append(f"{indent}}}")
    return lines


def _generate_server_block_content(
    host: ProxyHost,
    backend: str,
    is_https: bool = False,
    cert: Optional[Certificate] = None,
    indent: str = "    "
) -> list[str]:
    """Generate server block content (shared between HTTP and HTTPS)"""
    lines = []

    # Recover the true visitor IP from whatever sits in front of this host.
    # Without the right header here, every request would be logged, geo-located,
    # rate-limited and threat-scored against the CDN's edge address instead of
    # the actual client.
    real_ip_header = CDN_REAL_IP_HEADERS.get(
        getattr(host, "cdn_provider", None) or "none",
        CDN_REAL_IP_HEADERS["none"],
    )
    cdn_provider = getattr(host, "cdn_provider", None) or "none"
    provider_ranges = _TRUSTED_PROXY_RANGES.get(cdn_provider) or []
    if provider_ranges:
        # Defining set_real_ip_from here overrides the inherited http-level list
        # entirely, which is what we want: a Cloudflare-fronted host should trust
        # a CF-Connecting-IP header from Cloudflare's edge and nobody else --
        # not from every other CDN's range, and not from the LAN.
        lines.append(f"{indent}# Trusted {cdn_provider} edge ranges")
        for cidr in provider_ranges:
            lines.append(f"{indent}set_real_ip_from {cidr};")
    lines.append(f"{indent}real_ip_header {real_ip_header};")
    lines.append(f"{indent}real_ip_recursive on;")
    lines.append("")

    # Server-level settings
    lines.append(f"{indent}client_max_body_size {host.client_max_body_size};")

    if not host.proxy_buffering:
        lines.append(f"{indent}proxy_buffering off;")
    else:
        lines.append(f"{indent}proxy_buffer_size {host.proxy_buffer_size};")
        lines.append(f"{indent}proxy_buffers {host.proxy_buffers};")

    lines.append("")

    # Custom error pages
    if host.custom_error_pages:
        for code, page in host.custom_error_pages.items():
            lines.append(f"{indent}error_page {code} {page};")
        lines.append("")

    # Proxy host ID and honeypot flag for Lua
    lines.append(f'{indent}set $proxy_host_id "{host.id}";')
    lines.append(f'{indent}set $honeypot_enabled "{1 if host.honeypot_enabled else 0}";')
    lines.append("")

    # IP access list (if configured)
    lines.extend(_generate_access_list_rules(host, indent))

    # Auth wall (if configured)
    if host.auth_wall_id:
        lines.append(f"{indent}# Auth wall: {host.auth_wall_id}")
        lines.append(f'{indent}set $auth_wall_id "{host.auth_wall_id}";')
        # Auth type and name are fetched from API cache, but can be set here if available
        if hasattr(host, 'auth_wall') and host.auth_wall:
            lines.append(f'{indent}set $auth_wall_type "{host.auth_wall.auth_type or "multi"}";')
            lines.append(f'{indent}set $auth_wall_name "{host.auth_wall.name or "Protected"}";')
        else:
            lines.append(f'{indent}set $auth_wall_type "multi";')
            lines.append(f'{indent}set $auth_wall_name "Protected";')

    # Note: access_by_lua_block is now inside the default location (/)
    # This prevents auth from applying to /__auth/ and /api/auth-portal/ locations

    # Auth portal locations (static files and API) - only if auth wall is configured
    if host.auth_wall_id:
        # Get theme from auth wall config (default to 'default')
        theme = "default"
        if hasattr(host, 'auth_wall') and host.auth_wall and hasattr(host.auth_wall, 'theme'):
            theme = host.auth_wall.theme or "default"

        # Auth portal - Static assets (JS, CSS, images) with long cache
        lines.append(f"{indent}# Auth portal - Static assets (theme: {theme})")
        lines.append(f"{indent}location /__auth/assets/ {{")
        lines.append(f"{indent}    alias /var/www/auth-portal/{theme}/assets/;")
        lines.append(f"{indent}    add_header Cache-Control \"public, max-age=31536000, immutable\";")
        lines.append(f"{indent}}}")
        lines.append("")
        lines.append(f"{indent}location = /__auth/favicon.svg {{")
        lines.append(f"{indent}    alias /var/www/auth-portal/{theme}/favicon.svg;")
        lines.append(f"{indent}    add_header Cache-Control \"public, max-age=3600\";")
        lines.append(f"{indent}}}")
        lines.append("")
        # Auth portal - SPA fallback for client-side routes (e.g. /__auth/login)
        lines.append(f"{indent}# Auth portal - SPA fallback")
        lines.append(f"{indent}location /__auth/ {{")
        lines.append(f"{indent}    alias /var/www/auth-portal/{theme}/;")
        lines.append(f"{indent}    index index.html;")
        # The fallback is a URI, not a file: it must stay under /__auth/ so it lands back in
        # this location. A bare /index.html falls through to `location /` and the backend.
        lines.append(f"{indent}    try_files $uri $uri/ /__auth/index.html;")
        lines.append(f"{indent}    add_header Cache-Control \"no-cache\";")
        lines.append(f"{indent}}}")
        lines.append("")

        # API endpoints still proxied to backend
        lines.append(f"{indent}# Auth portal - API endpoints (NO auth check)")
        lines.append(f"{indent}location /api/auth-portal/ {{")
        lines.append(f"{indent}    set $auth_portal_api \"{settings.auth_portal_api_url.replace('http://', '')}\";")
        lines.append(f"{indent}    proxy_pass http://$auth_portal_api;")
        lines.append(f"{indent}    proxy_http_version 1.1;")
        lines.append(f"{indent}    proxy_set_header Host $host;")
        lines.append(f"{indent}    proxy_set_header X-Real-IP $remote_addr;")
        lines.append(f"{indent}    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;")
        lines.append(f"{indent}    proxy_set_header X-Forwarded-Proto $scheme;")
        lines.append(f"{indent}    proxy_set_header X-Forwarded-Host $host;")
        lines.append(f"{indent}")
        lines.append(f"{indent}    # Ensure cookies are passed through and not cached")
        lines.append(f"{indent}    proxy_pass_header Set-Cookie;")
        lines.append(f'{indent}    add_header Cache-Control "no-store, no-cache, must-revalidate";')
        lines.append(f"{indent}}}")
        lines.append("")

    # Traffic logging (if enabled)
    if host.traffic_logging_enabled:
        lines.append(f"{indent}# Traffic logging")
        lines.append(f"{indent}log_by_lua_file /usr/local/openresty/nginx/lua/traffic_logger.lua;")
        lines.append("")

    # Server-level advanced config
    if host.server_advanced_config:
        lines.append(f"{indent}# Server-level advanced config")
        for line in host.server_advanced_config.strip().split("\n"):
            lines.append(f"{indent}{line}")
        lines.append("")

    # ACME challenge location (always first on HTTP, also on HTTPS for good measure)
    lines.append(f"{indent}location /.well-known/acme-challenge/ {{")
    lines.append(f"{indent}    root /var/www/certbot;")
    if host.access_list_id:
        # Let's Encrypt must reach this whatever the host's IP access list says
        lines.append(f"{indent}    allow all;")
    lines.append(f"{indent}}}")
    lines.append("")

    # Custom locations (sorted by priority desc, then by specificity)
    locations = sorted(
        [loc for loc in (host.locations or []) if loc.enabled],
        key=lambda l: (-l.priority, -len(l.path))
    )

    for location in locations:
        lines.extend(_generate_location_block(location, host, indent))
        lines.append("")

    # Default location (from host settings)
    lines.extend(_generate_default_location(host, backend, indent))

    return lines


def generate_server_block(host: ProxyHost, cert: Optional[Certificate] = None) -> str:
    """Generate complete nginx server block for a proxy host"""
    domains = " ".join(host.domain_names)
    config_lines = []

    # Rate limit zone (placed before server block)
    rate_limit_zone = _generate_rate_limit_zone(host)
    if rate_limit_zone:
        config_lines.append(rate_limit_zone)
        config_lines.append("")

    # Cache path definition (placed before server block)
    cache_path = _generate_cache_path(host)
    if cache_path:
        config_lines.append(cache_path)
        config_lines.append("")

    # Upstream definition
    upstream_block = generate_upstream_block(host)
    if upstream_block:
        connection_map = generate_upstream_connection_map(host)
        if connection_map:
            config_lines.append(connection_map)
            config_lines.append("")
        config_lines.append(upstream_block)
        config_lines.append("")

    # Determine backend target: the upstream group when the host has enabled
    # upstream servers, otherwise the single forward host exactly as before.
    if uses_upstream_group(host):
        backend = upstream_name(host)
    else:
        backend = f"{host.forward_host}:{host.forward_port}"

    # HTTP server block
    config_lines.append("server {")
    config_lines.append("    listen 80;")
    config_lines.append(f"    server_name {domains};")
    config_lines.append("")

    # Check if we have a valid SSL cert
    has_valid_cert = cert and cert.certificate and cert.certificate_key

    if host.ssl_enabled and has_valid_cert:
        # Redirect HTTP to HTTPS (except ACME challenges)
        config_lines.append("    location /.well-known/acme-challenge/ {")
        config_lines.append("        root /var/www/certbot;")
        config_lines.append("    }")
        config_lines.append("")
        config_lines.append("    location / {")
        config_lines.append("        return 301 https://$host$request_uri;")
        config_lines.append("    }")
    else:
        # No SSL or no cert yet - serve content on HTTP
        config_lines.extend(_generate_server_block_content(host, backend, is_https=False))

    config_lines.append("}")
    config_lines.append("")

    # HTTPS server block - only if certificate has actual data
    if host.ssl_enabled and has_valid_cert:
        config_lines.append("server {")
        config_lines.append("    listen 443 ssl;")
        if host.http2_support:
            config_lines.append("    http2 on;")
        config_lines.append(f"    server_name {domains};")
        config_lines.append("")

        # SSL certificate
        cert_path = f"/etc/nginx/certs/{cert.id}.crt"
        key_path = f"/etc/nginx/certs/{cert.id}.key"
        config_lines.append(f"    ssl_certificate {cert_path};")
        config_lines.append(f"    ssl_certificate_key {key_path};")
        config_lines.append("")

        # HSTS
        if host.hsts_enabled:
            hsts_value = "max-age=31536000"
            if host.hsts_subdomains:
                hsts_value += "; includeSubDomains"
            config_lines.append(f'    add_header Strict-Transport-Security "{hsts_value}" always;')
            config_lines.append("")

        # Server block content
        config_lines.extend(_generate_server_block_content(host, backend, is_https=True, cert=cert))

        config_lines.append("}")

    return "\n".join(config_lines)


async def write_certificate_files(cert: Certificate) -> None:
    """Write certificate files to disk"""
    if not cert.certificate or not cert.certificate_key:
        return

    cert_path = os.path.join(settings.certificates_path, f"{cert.id}.crt")
    key_path = os.path.join(settings.certificates_path, f"{cert.id}.key")

    # Write certificate
    with open(cert_path, "w") as f:
        f.write(cert.certificate)
        if cert.certificate_chain:
            f.write("\n")
            f.write(cert.certificate_chain)

    # Write key (decrypt first)
    try:
        key_content = decrypt_data(cert.certificate_key)
    except Exception:
        key_content = cert.certificate_key  # Already decrypted or plain

    with open(key_path, "w") as f:
        f.write(key_content)

    # Set permissions
    os.chmod(key_path, 0o600)


def ensure_default_certificate() -> None:
    """Create the self-signed fallback certificate the default site serves on 443.

    `_default.conf` (and the kill switch) point at default.crt/default.key. On a
    fresh install nothing had created them, so every `nginx -t` failed and no
    proxy host could be saved. Existing files are never touched.
    """
    cert_dir = settings.certificates_path
    crt = os.path.join(cert_dir, "default.crt")
    key = os.path.join(cert_dir, "default.key")
    if os.path.exists(crt) and os.path.exists(key):
        return
    from datetime import datetime, timedelta, timezone

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    os.makedirs(cert_dir, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ghostwire-proxy-default")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )
    with open(key, "wb") as f:
        f.write(private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
    os.chmod(key, 0o600)
    with open(crt, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    logger.info("Created the self-signed default certificate for the default site")


async def generate_default_site_config(db: AsyncSession) -> str:
    """Generate the default site nginx config for direct IP / unknown host access.

    Behaviors:
    - congratulations: Show a Ghostwire Proxy welcome page
    - redirect: 301 redirect to a configured URL
    - 404: Return 404 Not Found
    - 444: Drop the connection (no response)
    """
    # The fallback certificate it serves on 443
    try:
        ensure_default_certificate()
    except OSError as e:
        logger.error(f"Could not create the default certificate: {e}")
    from app.models.setting import Setting

    # Read settings from DB
    behavior = "congratulations"
    redirect_url = ""

    result = await db.execute(
        select(Setting).where(Setting.key == "default_site_behavior")
    )
    setting = result.scalar_one_or_none()
    if setting:
        behavior = setting.value

    result = await db.execute(
        select(Setting).where(Setting.key == "default_site_redirect_url")
    )
    setting = result.scalar_one_or_none()
    if setting and setting.value:
        redirect_url = setting.value

    lines = [
        "# Default site — handles direct IP access and unknown hostnames",
        "# Auto-generated by Ghostwire Proxy — do not edit manually",
        "server {",
        "    listen 80 default_server;",
        "    listen 443 ssl default_server;",
        "    server_name _;",
        "",
        "    # Self-signed fallback cert for HTTPS on default site",
        "    ssl_certificate /etc/nginx/certs/default.crt;",
        "    ssl_certificate_key /etc/nginx/certs/default.key;",
        "",
        "    # Serve ACME challenges for hosts that don't have a server block yet",
        "    location /.well-known/acme-challenge/ {",
        "        root /var/www/certbot;",
        "    }",
        "",
    ]

    # The behaviours below live inside `location /`: a server-level `return` runs before nginx
    # picks a location, so it would also answer the ACME challenge above.
    if behavior == "redirect" and redirect_url:
        lines.extend([
            "    location / {",
            f"        return 301 {redirect_url};",
            "    }",
        ])
    elif behavior == "404":
        lines.extend([
            "    location / {",
            "        return 404;",
            "    }",
        ])
    elif behavior == "444":
        lines.extend([
            "    location / {",
            "        # Drop connection — send no response",
            "        return 444;",
            "    }",
        ])
    else:
        # congratulations (default) — show welcome page
        lines.extend([
            "    location / {",
            *_WELCOME_PAGE,
            "    }",
        ])

    lines.append("}")
    return "\n".join(lines) + "\n"


async def generate_all_configs(db: AsyncSession) -> list[str]:
    """Generate all proxy host configurations"""
    # Get all enabled proxy hosts with their locations and auth walls
    result = await db.execute(
        select(ProxyHost)
        .options(
            selectinload(ProxyHost.upstream_servers),
            selectinload(ProxyHost.locations),
            selectinload(ProxyHost.auth_wall),
            selectinload(ProxyHost.access_list).selectinload(AccessList.entries),
        )
        .where(ProxyHost.enabled == True)
    )
    hosts = result.scalars().all()

    # Load the CDN edge ranges once per generation run so each server block can
    # scope its own trust list.
    try:
        from app.services.trusted_proxy_service import get_ranges
        set_trusted_proxy_ranges(await get_ranges(db))
    except Exception as e:
        logger.warning(f"Could not load trusted proxy ranges: {e}")

    generated_files = []

    # Generate default site config
    default_conf = await generate_default_site_config(db)
    default_path = os.path.join(settings.nginx_config_path, "_default.conf")
    with open(default_path, "w") as f:
        f.write(default_conf)
    generated_files.append(default_path)

    for host in hosts:
        # Get certificate if SSL enabled
        cert = None
        if host.ssl_enabled and host.certificate_id:
            cert_result = await db.execute(
                select(Certificate).where(Certificate.id == host.certificate_id)
            )
            cert = cert_result.scalar_one_or_none()

            # Write certificate files
            if cert:
                await write_certificate_files(cert)

        # Generate config
        config = generate_server_block(host, cert)

        # Write config file
        config_path = os.path.join(settings.nginx_config_path, f"{host.id}.conf")
        with open(config_path, "w") as f:
            f.write(config)

        generated_files.append(config_path)

    return generated_files


async def remove_config(host_id: str) -> bool:
    """Remove proxy host configuration file"""
    config_path = os.path.join(settings.nginx_config_path, f"{host_id}.conf")
    if os.path.exists(config_path):
        os.remove(config_path)
        return True
    return False


logger = logging.getLogger(__name__)

BACKUP_DIR = "/data/backups/nginx-configs"
NGINX_CONTAINER = "ghostwire-proxy-nginx"
DOCKER_SOCKET = "/var/run/docker.sock"


def backup_configs() -> bool:
    """Backup all current nginx .conf files before generating new ones."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        # Clear old backup
        for f in glob.glob(os.path.join(BACKUP_DIR, "*.conf")):
            os.remove(f)
        # Copy current configs
        for f in glob.glob(os.path.join(settings.nginx_config_path, "*.conf")):
            shutil.copy2(f, os.path.join(BACKUP_DIR, os.path.basename(f)))
        return True
    except Exception as e:
        logger.error(f"Failed to backup nginx configs: {e}")
        return False


def restore_configs() -> bool:
    """Restore nginx .conf files from backup after a failed config test."""
    try:
        if not os.path.isdir(BACKUP_DIR):
            logger.warning("No backup directory found — cannot restore")
            return False
        # Remove the bad configs
        for f in glob.glob(os.path.join(settings.nginx_config_path, "*.conf")):
            os.remove(f)
        # Restore from backup
        for f in glob.glob(os.path.join(BACKUP_DIR, "*.conf")):
            shutil.copy2(f, os.path.join(settings.nginx_config_path, os.path.basename(f)))
        logger.info("Restored nginx configs from backup")
        return True
    except Exception as e:
        logger.error(f"Failed to restore nginx configs: {e}")
        return False


def _docker_api(request: bytes, read_timeout: float = 20.0) -> bytes:
    """Send a raw HTTP request to the Docker socket and read the whole response.

    Every caller sends `Connection: close`, so reading to EOF returns the full
    response without having to parse Content-Length or handle keep-alive.
    """
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(read_timeout)
    try:
        sock.connect(DOCKER_SOCKET)
        sock.sendall(request)
        chunks = []
        while True:
            try:
                data = sock.recv(65536)
            except socket.timeout:
                break
            if not data:
                break
            chunks.append(data)
        return b"".join(chunks)
    finally:
        sock.close()


def _http_body(raw: bytes) -> bytes:
    """Strip HTTP headers, de-chunking the body if it came back chunked."""
    split = raw.find(b"\r\n\r\n")
    if split == -1:
        return b""
    headers, body = raw[:split].lower(), raw[split + 4:]
    if b"transfer-encoding: chunked" not in headers:
        return body

    decoded = bytearray()
    while True:
        line_end = body.find(b"\r\n")
        if line_end == -1:
            break
        try:
            size = int(body[:line_end].split(b";")[0], 16)
        except ValueError:
            break
        if size == 0:
            break
        decoded += body[line_end + 2:line_end + 2 + size]
        body = body[line_end + 2 + size + 2:]
    return bytes(decoded)


def _demux_docker_stream(body: bytes) -> str:
    """Decode Docker's multiplexed exec stream (8-byte header per frame)."""
    out = []
    i = 0
    while i + 8 <= len(body):
        if body[i] not in (0, 1, 2) or body[i + 1:i + 4] != b"\x00\x00\x00":
            # Not multiplexed (TTY mode) — the remainder is plain output.
            return body[i:].decode("utf-8", "replace")
        size = int.from_bytes(body[i + 4:i + 8], "big")
        i += 8
        out.append(body[i:i + size].decode("utf-8", "replace"))
        i += size
    return "".join(out)


def test_nginx_config() -> tuple[bool, str]:
    """Run `nginx -t` and return (passed, nginx's own output).

    The output is the point: on failure nginx names the offending file, line
    number and directive, and that message is what gets shown to the admin.
    """
    if not os.path.exists(DOCKER_SOCKET):
        # Fallback: local nginx -t (works when running outside Docker)
        try:
            result = subprocess.run(
                ["nginx", "-t"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            output = (result.stderr or result.stdout).strip()
            return result.returncode == 0, output or "nginx -t produced no output"
        except Exception as e:
            return False, str(e)

    try:
        import json as _json

        # Create the exec instance, attached so its output can be read back.
        exec_body = _json.dumps({
            "Cmd": ["nginx", "-t"],
            "AttachStdout": True,
            "AttachStderr": True,
        })
        created = _http_body(_docker_api(
            f"POST /containers/{NGINX_CONTAINER}/exec HTTP/1.1\r\n"
            f"Host: localhost\r\n"
            f"Content-Type: application/json\r\n"
            f"Connection: close\r\n"
            f"Content-Length: {len(exec_body)}\r\n\r\n"
            f"{exec_body}".encode(),
            read_timeout=10.0,
        ))
        exec_id = _json.loads(created or b"{}").get("Id")
        if not exec_id:
            detail = created[:200].decode("utf-8", "replace")
            return False, f"Failed to create nginx -t exec: {detail}"

        # Start it attached (Detach=False) and read the multiplexed stream to
        # completion — this blocks until nginx -t has actually finished.
        start_body = _json.dumps({"Detach": False, "Tty": False})
        started = _docker_api(
            f"POST /exec/{exec_id}/start HTTP/1.1\r\n"
            f"Host: localhost\r\n"
            f"Content-Type: application/json\r\n"
            f"Connection: close\r\n"
            f"Content-Length: {len(start_body)}\r\n\r\n"
            f"{start_body}".encode()
        )
        output = _demux_docker_stream(_http_body(started)).strip()

        # The exec has exited by now, so its exit code is available.
        inspected = _http_body(_docker_api(
            "GET /exec/{}/json HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Connection: close\r\n\r\n".format(exec_id).encode(),
            read_timeout=10.0,
        ))
        exit_code = _json.loads(inspected or b"{}").get("ExitCode")

        if exit_code == 0:
            return True, output or "nginx config test passed"
        if exit_code is None:
            return False, f"nginx -t did not report an exit code. Output: {output}"
        return False, output or f"nginx -t failed (exit code {exit_code})"

    except Exception as e:
        return False, str(e)


def reload_nginx() -> tuple[bool, str]:
    """Reload nginx configuration via Docker socket SIGHUP"""
    docker_socket = DOCKER_SOCKET
    if not os.path.exists(docker_socket):
        return False, "Docker socket not available — mount /var/run/docker.sock in the API container"

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(docker_socket)
        request = (
            f"POST /containers/{NGINX_CONTAINER}/kill?signal=HUP HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Content-Length: 0\r\n\r\n"
        )
        sock.sendall(request.encode())
        response = sock.recv(4096).decode()
        sock.close()

        # Check HTTP status from Docker API
        if "204" in response[:30] or "200" in response[:30]:
            return True, "Nginx reloaded successfully"
        elif "404" in response[:30]:
            return False, f"Nginx container '{NGINX_CONTAINER}' not found"
        else:
            status_line = response.split("\r\n", 1)[0] if response else "empty response"
            return False, f"Docker API returned: {status_line}"
    except Exception as e:
        return False, str(e)
