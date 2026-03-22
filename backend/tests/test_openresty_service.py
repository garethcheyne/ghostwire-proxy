"""Tests for openresty service — nginx config generation."""

import pytest
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
        host.id = "abc-123"
        host.upstream_servers = [server]

        result = generate_upstream_block(host)
        assert "upstream" in result
        assert "backend:8080" in result


class TestGenerateServerBlock:
    """Tests for server block generation."""

    def test_http_server_block(self):
        host = MagicMock(spec=ProxyHost)
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


class TestNginxOperations:
    """Tests for nginx test and reload."""

    def test_test_nginx_config_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test is successful"

        with patch("subprocess.run", return_value=mock_result):
            success, output = test_nginx_config()

        assert success is True

    def test_test_nginx_config_failure(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "syntax error"

        with patch("subprocess.run", return_value=mock_result):
            success, output = test_nginx_config()

        assert success is False

    def test_reload_nginx_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "signal sent"

        with patch("subprocess.run", return_value=mock_result):
            success, output = reload_nginx()

        assert success is True

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
