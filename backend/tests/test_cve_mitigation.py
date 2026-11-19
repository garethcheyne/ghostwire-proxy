"""CVE mitigations: the switch, how config generation honours it, and the routes that set it."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.audit_log import AuditLog
from app.models.proxy_host import ProxyHost
from app.models.setting import Setting
from app.services import cve_mitigation_service, openresty_service
from app.services.openresty_service import generate_server_block
from sqlalchemy import select

INTERNAL = {"X-Internal-Auth": "test-internal-token"}


@pytest.fixture(autouse=True)
def no_mitigations():
    openresty_service.set_cve_mitigations(())
    yield
    openresty_service.set_cve_mitigations(())


@pytest.fixture
def nginx(tmp_path, monkeypatch):
    """Real config generation into a temp dir; nginx -t and reload are stubbed (and inspectable)."""
    monkeypatch.setattr(openresty_service.settings, "nginx_config_path", str(tmp_path / "conf"))
    monkeypatch.setattr(openresty_service.settings, "certificates_path", str(tmp_path / "certs"))
    monkeypatch.setattr(openresty_service, "BACKUP_DIR", str(tmp_path / "backup"))
    (tmp_path / "conf").mkdir()
    (tmp_path / "certs").mkdir()
    stubs = MagicMock()
    stubs.test.return_value = (True, "ok")
    stubs.reload.return_value = (True, "ok")
    with (
        patch("app.api.routes.proxy_hosts.test_nginx_config", stubs.test),
        patch("app.api.routes.proxy_hosts.reload_nginx", stubs.reload),
        patch("app.api.routes.proxy_hosts.cache_delete_prefix", new=AsyncMock()),
        patch("app.services.openresty_service.ensure_default_certificate"),
    ):
        stubs.conf = tmp_path / "conf"
        yield stubs


async def add_http2_host(db) -> ProxyHost:
    host = ProxyHost(
        domain_names=["shop.example.com"],
        forward_scheme="http",
        forward_host="10.0.0.5",
        forward_port=8080,
        ssl_enabled=False,
        http2_support=True,
        enabled=True,
    )
    db.add(host)
    await db.commit()
    return host


def ssl_host():
    host = MagicMock(spec=ProxyHost)
    for key, value in {
        "id": "h",
        "domain_names": ["a.example.com"],
        "forward_scheme": "http",
        "forward_host": "10.0.0.5",
        "forward_port": 80,
        "ssl_enabled": True,
        "ssl_forced": False,
        "http2_support": True,
        "hsts_enabled": False,
        "hsts_subdomains": False,
        "block_common_exploits": False,
        "websocket_support": False,
        "cache_enabled": False,
        "access_list_id": None,
        "auth_wall_id": None,
        "custom_nginx_config": "",
        "advanced_config": "",
        "upstream_servers": [],
        "locations": [],
        "rate_limit_requests": 100,
        "rate_limit_period": "1s",
    }.items():
        setattr(host, key, value)
    return host


class TestConfigGeneration:
    def test_http2_on_without_the_mitigation(self):
        assert "    http2 on;" in generate_server_block(ssl_host(), MagicMock()).splitlines()

    def test_mitigation_leaves_http2_out(self):
        openresty_service.set_cve_mitigations({"disable_http2"})
        config = generate_server_block(ssl_host(), MagicMock())
        assert "http2 on;" not in config
        assert "disable_http2" in config  # says why, for whoever reads the file

    def test_a_host_without_http2_is_unchanged(self):
        host, cert = ssl_host(), MagicMock()
        host.http2_support = False
        before = generate_server_block(host, cert)
        openresty_service.set_cve_mitigations({"disable_http2"})
        assert generate_server_block(host, cert) == before


class TestService:
    async def test_on_then_off_regenerates_and_keeps_the_host_setting(self, db_session, nginx):
        host = await add_http2_host(db_session)

        ok, _ = await cve_mitigation_service.set_mitigation(db_session, "disable_http2", True, ["CVE-2026-123007"])
        assert ok
        assert await cve_mitigation_service.active_mitigations(db_session) == {"disable_http2"}
        assert nginx.reload.called
        await db_session.refresh(host)
        assert host.http2_support is True  # the host's own setting is untouched

        ok, _ = await cve_mitigation_service.set_mitigation(db_session, "disable_http2", False)
        assert ok
        assert await cve_mitigation_service.active_mitigations(db_session) == set()

    async def test_a_failed_nginx_test_saves_nothing(self, db_session, nginx):
        nginx.test.return_value = (False, "nginx: [emerg] something")
        ok, message = await cve_mitigation_service.set_mitigation(db_session, "disable_http2", True)
        assert not ok
        assert "emerg" in message
        assert await cve_mitigation_service.active_mitigations(db_session) == set()
        audit = await db_session.execute(select(AuditLog).where(AuditLog.action.like("cve_mitigation%")))
        assert audit.scalars().all() == []
        assert not nginx.reload.called

    async def test_an_audit_entry_records_it(self, db_session, nginx):
        await cve_mitigation_service.set_mitigation(db_session, "disable_http2", True, ["CVE-2026-123007", "x;rm"])
        entry = (await db_session.execute(select(AuditLog).where(AuditLog.action == "cve_mitigation_on"))).scalar_one()
        assert '"CVE-2026-123007"' in entry.details
        assert "x;rm" not in entry.details  # only well-formed ids are kept

    async def test_unknown_name(self, db_session):
        with pytest.raises(ValueError, match="Unknown mitigation"):
            await cve_mitigation_service.set_mitigation(db_session, "reboot_everything", True)


class TestInternalRoutes:
    async def test_needs_the_internal_token(self, client):
        assert (await client.get("/api/internal/cve/mitigations")).status_code in (401, 403)
        res = await client.put("/api/internal/cve/mitigations/disable_http2", json={"active": True})
        assert res.status_code in (401, 403)

    async def test_on_and_listed(self, client, nginx):
        res = await client.put(
            "/api/internal/cve/mitigations/disable_http2",
            headers=INTERNAL,
            json={"active": True, "cves": ["CVE-2026-123007"]},
        )
        assert res.status_code == 200, res.text
        listed = (await client.get("/api/internal/cve/mitigations", headers=INTERNAL)).json()
        assert listed["active"] == ["disable_http2"]
        assert "disable_http2" in listed["available"]

    async def test_unknown_name_is_404(self, client):
        res = await client.put("/api/internal/cve/mitigations/nope", headers=INTERNAL, json={"active": True})
        assert res.status_code == 404

    async def test_nginx_refusing_it_is_409(self, client, nginx):
        nginx.test.return_value = (False, "bad")
        res = await client.put("/api/internal/cve/mitigations/disable_http2", headers=INTERNAL, json={"active": True})
        assert res.status_code == 409


class TestAdminRoutes:
    async def test_admin_can_turn_it_off(self, client, auth_headers, nginx):
        res = await client.put(
            "/api/updates/cve/mitigations/disable_http2", headers=auth_headers, json={"active": False}
        )
        assert res.status_code == 200, res.text

    async def test_not_for_regular_users(self, client, user_auth_headers):
        res = await client.get("/api/updates/cve/mitigations", headers=user_auth_headers)
        assert res.status_code == 403


async def test_generic_settings_route_refuses_the_key(client, auth_headers, db_session):
    res = await client.put("/api/settings/cve_mitigation_disable_http2", headers=auth_headers, json={"value": "true"})
    assert res.status_code == 422
    assert (await db_session.get(Setting, "cve_mitigation_disable_http2")) is None
