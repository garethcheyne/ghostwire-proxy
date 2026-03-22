"""
OpenResty/Nginx configuration generation service.
Generates nginx server blocks from ProxyHost database records.
Supports multiple locations, caching, rate limiting, and custom headers.
"""
import os
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


def _safe_id(id_str: str) -> str:
    """Convert UUID to nginx-safe identifier"""
    return id_str.replace('-', '_')


def generate_upstream_block(host: ProxyHost) -> str:
    """Generate upstream block for load balancing"""
    if not host.upstream_servers or len(host.upstream_servers) == 0:
        return ""

    lines = [f"upstream upstream_{_safe_id(host.id)} {{"]

    for server in host.upstream_servers:
        if server.enabled:
            server_line = f"    server {server.host}:{server.port}"
            if server.weight != 1:
                server_line += f" weight={server.weight}"
            if server.max_fails != 3:
                server_line += f" max_fails={server.max_fails}"
            if server.fail_timeout != 30:
                server_line += f" fail_timeout={server.fail_timeout}s"
            server_line += ";"
            lines.append(server_line)

    lines.append("    keepalive 32;")
    lines.append("}")
    return "\n".join(lines)


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
    rate = f"{host.rate_limit_requests}r/{host.rate_limit_period}"
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

    # Auth wall + WAF inside the default location
    if host.auth_wall_id and host.block_exploits:
        lines.append(f"{indent}    access_by_lua_block {{")
        lines.append(f"{indent}        require('auth_wall').access()")
        lines.append(f"{indent}        require('waf').access()")
        lines.append(f"{indent}    }}")
    elif host.auth_wall_id:
        lines.append(f"{indent}    access_by_lua_block {{ require('auth_wall').access() }}")
    elif host.block_exploits:
        lines.append(f"{indent}    access_by_lua_block {{ require('waf').access() }}")

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
        lines.append(f"{indent}    proxy_set_header Connection $connection_upgrade;")

    # Timeouts
    lines.append("")
    lines.append(f"{indent}    proxy_connect_timeout 60s;")
    lines.append(f"{indent}    proxy_send_timeout 60s;")
    lines.append(f"{indent}    proxy_read_timeout 60s;")

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

    # Access control (if configured)
    if host.access_list_id:
        lines.append(f"{indent}# Access list: {host.access_list_id}")
        lines.append(f"{indent}access_by_lua_file /usr/local/openresty/nginx/lua/access_control.lua;")
        lines.append("")

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

        # Auth portal - Static files served directly from nginx (self-contained, no UI dependency)
        lines.append(f"{indent}# Auth portal - Static files (theme: {theme})")
        lines.append(f"{indent}location /__auth/ {{")
        lines.append(f"{indent}    alias /var/www/auth-portal/{theme}/;")
        lines.append(f"{indent}    index index.html;")
        lines.append(f"{indent}    try_files $uri $uri/ /__auth/index.html;")
        lines.append(f"{indent}    add_header Cache-Control \"public, max-age=3600\";")
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
        config_lines.append(upstream_block)
        config_lines.append("")

    # Determine backend target
    if host.upstream_servers and len(host.upstream_servers) > 0:
        backend = f"upstream_{_safe_id(host.id)}"
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


async def generate_default_site_config(db: AsyncSession) -> str:
    """Generate the default site nginx config for direct IP / unknown host access.

    Behaviors:
    - congratulations: Show a Ghostwire Proxy welcome page
    - redirect: 301 redirect to a configured URL
    - 404: Return 404 Not Found
    - 444: Drop the connection (no response)
    """
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
    ]

    if behavior == "redirect" and redirect_url:
        lines.extend([
            f"    return 301 {redirect_url};",
        ])
    elif behavior == "404":
        lines.extend([
            "    return 404;",
        ])
    elif behavior == "444":
        lines.extend([
            "    # Drop connection — send no response",
            "    return 444;",
        ])
    else:
        # congratulations (default) — show welcome page
        lines.extend([
            "    location / {",
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
            selectinload(ProxyHost.auth_wall)
        )
        .where(ProxyHost.enabled == True)
    )
    hosts = result.scalars().all()

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


def test_nginx_config() -> tuple[bool, str]:
    """Test nginx configuration"""
    try:
        result = subprocess.run(
            ["nginx", "-t"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0, result.stderr
    except Exception as e:
        return False, str(e)


def reload_nginx() -> tuple[bool, str]:
    """Reload nginx configuration via Docker socket SIGHUP"""
    docker_socket = "/var/run/docker.sock"
    if not os.path.exists(docker_socket):
        return False, "Docker socket not available"

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(docker_socket)
        request = (
            "POST /containers/ghostwire-proxy-nginx/kill?signal=HUP HTTP/1.1\r\n"
            "Host: localhost\r\n"
            "Content-Length: 0\r\n\r\n"
        )
        sock.sendall(request.encode())
        sock.recv(4096)
        sock.close()
        return True, "Nginx reloaded successfully"
    except Exception as e:
        return False, str(e)
