"""Tests for openresty service — nginx config generation."""

import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.openresty_service import (
    generate_upstream_block,
    generate_server_block,
    generate_default_site_config,
    test_nginx_config,
    reload_nginx,
    remove_config,
)
from app.models.proxy_host import ProxyHost
from app.models.certificate import Certificate
from app.models.setting import Setting


class TestGenerateUpstreamBlock:
    """Tests for upstream block generation."""

    def test_empty_upstream_returns_empty(self):
        host = MagicMock(spec=ProxyHost)
        host.rate_limit_requests = 100
        host.rate_limit_period = "1s"
        host.id = "host-1"
        host.upstream_servers = []

        result = generate_upstream_block(host)
        assert result == ""

    def test_upstream_with_servers(self):
        server = MagicMock()
        server.enabled = True
        server.host = "backend"
        server.port = 8080
        server.weight = 1
        server.max_fails = 3
        server.fail_timeout = 30

        host = MagicMock(spec=ProxyHost)
        host.rate_limit_requests = 100
        host.rate_limit_period = "1s"
        host.id = "abc-123"
        host.upstream_servers = [server]

        result = generate_upstream_block(host)
        assert "upstream" in result
        assert "backend:8080" in result


class TestGenerateServerBlock:
    """Tests for server block generation."""

    def test_http_server_block(self):
        host = MagicMock(spec=ProxyHost)
        host.rate_limit_requests = 100
        host.rate_limit_period = "1s"
        host.id = "host-2"
        host.domain_names = ["example.com"]
        host.forward_scheme = "http"
        host.forward_host = "backend"
        host.forward_port = 8080
        host.ssl_enabled = False
        host.ssl_forced = False
        host.http2_support = False
        host.hsts_enabled = False
        host.block_common_exploits = False
        host.websocket_support = False
        host.cache_enabled = False
        host.access_list_id = None
        host.auth_wall_id = None
        host.custom_nginx_config = ""
        host.advanced_config = ""
        host.upstream_servers = []
        host.locations = []

        result = generate_server_block(host)
        assert "server_name example.com" in result
        assert "listen 80" in result

    def test_ssl_server_block(self):
        host = MagicMock(spec=ProxyHost)
        host.rate_limit_requests = 100
        host.rate_limit_period = "1s"
        host.id = "host-3"
        host.domain_names = ["secure.example.com"]
        host.forward_scheme = "https"
        host.forward_host = "backend"
        host.forward_port = 443
        host.ssl_enabled = True
        host.ssl_forced = True
        host.http2_support = True
        host.hsts_enabled = True
        host.hsts_subdomains = True
        host.block_common_exploits = False
        host.websocket_support = False
        host.cache_enabled = False
        host.access_list_id = None
        host.auth_wall_id = None
        host.custom_nginx_config = ""
        host.advanced_config = ""
        host.upstream_servers = []
        host.locations = []

        cert = MagicMock(spec=Certificate)
        cert.id = "cert-1"

        result = generate_server_block(host, cert)
        assert "ssl" in result.lower()
        assert "secure.example.com" in result

    def test_multiple_domains(self):
        host = MagicMock(spec=ProxyHost)
        host.rate_limit_requests = 100
        host.rate_limit_period = "1s"
        host.id = "host-4"
        host.domain_names = ["a.example.com", "b.example.com"]
        host.forward_scheme = "http"
        host.forward_host = "backend"
        host.forward_port = 80
        host.ssl_enabled = False
        host.ssl_forced = False
        host.http2_support = False
        host.hsts_enabled = False
        host.block_common_exploits = False
        host.websocket_support = False
        host.cache_enabled = False
        host.access_list_id = None
        host.auth_wall_id = None
        host.custom_nginx_config = ""
        host.advanced_config = ""
        host.upstream_servers = []
        host.locations = []

        result = generate_server_block(host)
        assert "a.example.com" in result
        assert "b.example.com" in result


def _host_with_access_list(mode, entries):
    host = MagicMock(spec=ProxyHost)
    host.rate_limit_requests = 100
    host.rate_limit_period = "1s"
    host.id = "host-acl"
    host.domain_names = ["acl.example.com"]
    host.forward_scheme = "http"
    host.forward_host = "backend"
    host.forward_port = 8080
    host.ssl_enabled = False
    host.hsts_enabled = False
    host.access_list_id = "acl-1"
    host.access_list = SimpleNamespace(
        id="acl-1",
        mode=mode,
        entries=[SimpleNamespace(ip_or_cidr=ip, action=action) for ip, action in entries],
    )
    host.auth_wall_id = None
    host.upstream_servers = []
    host.locations = []
    return host


class TestAccessListRules:
    """An assigned IP access list becomes nginx allow/deny rules."""

    def test_whitelist_allows_listed_then_denies_everyone_else(self):
        host = _host_with_access_list("whitelist", [("203.0.113.7", "allow"), ("10.0.0.0/8", "allow")])
        result = generate_server_block(host)
        assert "allow 203.0.113.7/32;" in result
        assert "allow 10.0.0.0/8;" in result
        assert result.index("allow 10.0.0.0/8;") < result.index("deny all;")

    def test_blacklist_denies_listed_then_allows_everyone_else(self):
        host = _host_with_access_list("blacklist", [("2001:db8::/32", "deny")])
        result = generate_server_block(host)
        assert "deny 2001:db8::/32;" in result
        assert result.index("deny 2001:db8::/32;") < result.index("allow all;")

    def test_rules_apply_before_any_location_and_acme_stays_reachable(self):
        host = _host_with_access_list("whitelist", [("203.0.113.7", "allow")])
        result = generate_server_block(host)
        assert result.index("deny all;") < result.index("location /")
        acme = result[result.index("location /.well-known/acme-challenge/"):]
        assert "allow all;" in acme[:acme.index("}")]

    def test_invalid_entry_is_skipped_not_written(self):
        host = _host_with_access_list("whitelist", [("1.2.3.4; return 200", "allow"), ("198.51.100.1", "allow")])
        result = generate_server_block(host)
        assert "return 200" not in result
        assert "allow 198.51.100.1/32;" in result

    def test_no_access_list_writes_no_rules(self):
        host = _host_with_access_list("whitelist", [])
        host.access_list_id = None
        result = generate_server_block(host)
        assert "deny all;" not in result
        assert "access_control.lua" not in result


class TestAccessListBlockedResponse:
    """A list can answer blocked visitors like the default site does."""

    def _render(self, behavior, url=None, custom_error_pages=None):
        host = _host_with_access_list("whitelist", [("203.0.113.7", "allow")])
        host.access_list.blocked_behavior = behavior
        host.access_list.blocked_redirect_url = url
        host.custom_error_pages = custom_error_pages or {}
        return generate_server_block(host)

    def test_403_keeps_nginx_default(self):
        assert "error_page 403" not in self._render("403")

    def test_redirect_sends_blocked_visitors_elsewhere(self):
        result = self._render("redirect", "https://example.org/")
        assert "error_page 403 = @ip_access_blocked;" in result
        assert "return 302 https://example.org/;" in result

    def test_blocked_location_is_reachable_despite_deny_all(self):
        result = self._render("444")
        named = result[result.index("location @ip_access_blocked {"):]
        assert "allow all;" in named[:named.index("}")]
        assert "return 444;" in named[:named.index("}")]

    def test_welcome_page(self):
        assert "<title>Ghostwire Proxy</title>" in self._render("congratulations")

    def test_custom_403_page_takes_precedence(self):
        assert "@ip_access_blocked" not in self._render("404", custom_error_pages={"403": "/403.html"})


class TestAuthPortal:
    """A walled host serves its login portal itself, never from the backend."""

    def test_spa_fallback_stays_inside_the_portal(self):
        # A fallback of /index.html leaves /__auth/, lands in `location /` and is
        # proxied to the backend - whose own login redirect then loops forever.
        host = _host_with_access_list("whitelist", [])
        host.access_list_id = None
        host.auth_wall_id = "wall-1"
        host.auth_wall = SimpleNamespace(auth_type="multi", name="Wall", theme="default")
        result = generate_server_block(host)
        portal = result[result.index("location /__auth/ {"):]
        portal = portal[:portal.index("}")]
        assert "try_files $uri $uri/ /__auth/index.html;" in portal


class TestGenerateDefaultSiteConfig:
    """Tests for default site config generation."""

    @pytest.mark.asyncio
    async def test_default_congratulations(self, db_session):
        config = await generate_default_site_config(db_session)
        assert "default_server" in config

    @pytest.mark.asyncio
    async def test_redirect_behavior(self, db_session):
        db_session.add(Setting(key="default_site_behavior", value="redirect"))
        db_session.add(Setting(key="default_site_redirect_url", value="https://google.com"))
        await db_session.commit()

        config = await generate_default_site_config(db_session)
        assert "301" in config or "redirect" in config.lower()

    @pytest.mark.asyncio
    async def test_404_behavior(self, db_session):
        db_session.add(Setting(key="default_site_behavior", value="404"))
        await db_session.commit()

        config = await generate_default_site_config(db_session)
        assert "404" in config

    @pytest.mark.asyncio
    async def test_444_drop_behavior(self, db_session):
        db_session.add(Setting(key="default_site_behavior", value="444"))
        await db_session.commit()

        config = await generate_default_site_config(db_session)
        assert "444" in config

    @pytest.mark.asyncio
    @pytest.mark.parametrize("behavior", ["congratulations", "redirect", "404", "444"])
    async def test_acme_challenges_served_for_every_behavior(self, db_session, behavior):
        """Certs for hosts without a server block are validated through the default site, so no
        behaviour may answer /.well-known/acme-challenge/ itself."""
        import re

        db_session.add(Setting(key="default_site_behavior", value=behavior))
        db_session.add(Setting(key="default_site_redirect_url", value="https://google.com"))
        await db_session.commit()

        config = await generate_default_site_config(db_session)
        assert "location /.well-known/acme-challenge/ {\n        root /var/www/certbot;" in config
        # A server-level `return` runs before location matching and would win.
        assert not re.search(r"^    return ", config, re.MULTILINE)


class TestNginxOperations:
    """Tests for nginx test and reload."""

    def test_test_nginx_config_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test is successful"

        with patch("subprocess.run", return_value=mock_result), \
             patch("os.path.exists", return_value=False):
            success, output = test_nginx_config()

        assert success is True

    def test_test_nginx_config_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "syntax error"

        with patch("subprocess.run", return_value=mock_result), \
             patch("os.path.exists", return_value=False):
            success, output = test_nginx_config()

        assert success is False

    def test_reload_nginx_success(self):
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b"HTTP/1.1 204 No Content\r\n"

        with patch("app.services.openresty_service.os.path.exists", return_value=True), \
             patch("app.services.openresty_service.socket.socket", return_value=mock_sock):
            success, output = reload_nginx()

        assert success is True
        mock_sock.connect.assert_called_once_with("/var/run/docker.sock")
        mock_sock.sendall.assert_called_once()
        mock_sock.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_config_file_exists(self):
        with patch("os.path.exists", return_value=True), \
             patch("os.remove") as mock_remove:
            result = await remove_config("host-123")

        assert result is True
        mock_remove.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_config_file_not_exists(self):
        with patch("os.path.exists", return_value=False):
            result = await remove_config("host-999")

        assert result is False
