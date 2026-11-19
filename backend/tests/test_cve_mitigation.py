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


class TestCustomSnippets:
    """A host's own snippets go in verbatim, so the mitigation has to reach into them too."""

    def config_with(self, field, snippet):
        host = ssl_host()
        host.server_advanced_config = ""
        host.advanced_config = ""
        setattr(host, field, snippet)
        return generate_server_block(host, MagicMock())

    def test_server_snippet_http2_is_forced_off(self):
        openresty_service.set_cve_mitigations({"disable_http2"})
        config = self.config_with("server_advanced_config", "client_max_body_size 50m;\n  http2 on;")
        assert "http2 on;" not in config
        assert "http2 off;" in config
        assert "client_max_body_size 50m;" in config  # the rest of the snippet is left alone

    def test_listen_http2_flag_is_dropped(self):
        openresty_service.set_cve_mitigations({"disable_http2"})
        config = self.config_with("server_advanced_config", "listen 8443 ssl http2;")
        assert "listen 8443 ssl;" in config

    def test_default_location_snippet_too(self):
        openresty_service.set_cve_mitigations({"disable_http2"})
        assert "http2 on;" not in self.config_with("advanced_config", "http2 on;")

    def test_comments_are_left_as_written(self):
        openresty_service.set_cve_mitigations({"disable_http2"})
        assert "# keep http2 on; later" in self.config_with("server_advanced_config", "# keep http2 on; later")

    def test_without_the_mitigation_snippets_are_untouched(self):
        assert "  http2 on;" in self.config_with("server_advanced_config", "a;\n  http2 on;")


class TestCveStatusRoute:
    async def test_no_report_yet(self, client, auth_headers, tmp_path, monkeypatch):
        monkeypatch.setattr(cve_mitigation_service, "REPORT_PATH", str(tmp_path / "cve-report.json"))
        body = (await client.get("/api/updates/cve", headers=auth_headers)).json()
        assert body["report"] is None
        assert body["error"] is None
        assert "disable_http2" in body["available_mitigations"]

    async def test_serves_the_last_report_and_live_mitigations(self, client, auth_headers, tmp_path, monkeypatch):
        path = tmp_path / "cve-report.json"
        path.write_text('{"schema": 1, "meta": {"checked_at": "2026-11-19T09:30:00Z"}, "advisories": []}')
        monkeypatch.setattr(cve_mitigation_service, "REPORT_PATH", str(path))
        body = (await client.get("/api/updates/cve", headers=auth_headers)).json()
        assert body["report"]["meta"]["checked_at"] == "2026-11-19T09:30:00Z"
        assert body["active_mitigations"] == []

    async def test_a_broken_report_is_an_error_not_a_crash(self, client, auth_headers, tmp_path, monkeypatch):
        path = tmp_path / "cve-report.json"
        path.write_text("{half a file")
        monkeypatch.setattr(cve_mitigation_service, "REPORT_PATH", str(path))
        body = (await client.get("/api/updates/cve", headers=auth_headers)).json()
        assert body["report"] is None
        assert "Couldn't read" in body["error"]

    async def test_admins_only(self, client, user_auth_headers):
        assert (await client.get("/api/updates/cve", headers=user_auth_headers)).status_code == 403


class TestDisabledHostsLeaveNginx:
    """A disabled host's config used to stay on disk, so nginx kept serving it and nothing regenerated it
    (on prod: two disabled hosts still had `http2 on;` after the mitigation)."""

    async def test_generation_removes_configs_of_hosts_that_arent_enabled(self, db_session, nginx):
        from app.services.openresty_service import generate_all_configs

        live = await add_http2_host(db_session)
        gone = await add_http2_host(db_session)
        gone.enabled = False
        await db_session.commit()
        conf = nginx.conf
        (conf / f"{gone.id}.conf").write_text("server { http2 on; }")
        (conf / "0b1e5c1e-0000-4000-8000-000000000000.conf").write_text("server {}")  # a deleted host's
        for keep in ("_kill_switch.conf", "custom-include.conf", f"{live.id}.conf.disabled"):
            (conf / keep).write_text("# not a host config this generation owns")

        await generate_all_configs(db_session)

        assert (conf / f"{live.id}.conf").exists()
        assert not (conf / f"{gone.id}.conf").exists()
        assert not (conf / "0b1e5c1e-0000-4000-8000-000000000000.conf").exists()
        for keep in ("_default.conf", "_kill_switch.conf", "custom-include.conf", f"{live.id}.conf.disabled"):
            assert (conf / keep).exists(), keep

    async def test_disabling_a_host_takes_it_out_of_nginx(self, client, auth_headers, db_session, nginx):
        host = await add_http2_host(db_session)
        res = await client.post(f"/api/proxy-hosts/{host.id}/enable", headers=auth_headers)
        assert res.status_code == 200, res.text
        assert (nginx.conf / f"{host.id}.conf").exists()

        res = await client.post(f"/api/proxy-hosts/{host.id}/disable", headers=auth_headers)
        assert res.status_code == 200, res.text
        assert not (nginx.conf / f"{host.id}.conf").exists()
