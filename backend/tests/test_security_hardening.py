"""Internal routes, client address resolution, secret settings, alert webhooks,
auth portal redirects, OAuth allow-lists and backup/restore safety."""

import json
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.client_ip import TrustedProxies, TrustedProxyMiddleware
from app.models.setting import Setting
from app.services.auth_portal_redirect import is_safe_redirect
from app.services.auth_wall_access import (
    clean_list,
    is_email_allowed,
    normalize_domain,
    normalize_email,
    open_to_any_account,
)
from app.services.outbound_url import OutboundUrlError, validate_outbound_url


# ── /api/internal/* ──────────────────────────────────────────────────────

INTERNAL_ROUTES = [
    ("post", "/api/internal/traffic/log", {}),
    ("post", "/api/internal/threats/log", {}),
    ("get", "/api/internal/waf/rules", None),
    ("get", "/api/internal/geoip/rules", None),
    ("get", "/api/internal/trusted-ips", None),
    ("get", "/api/internal/blocked-ips", None),
    ("get", "/api/internal/honeypot/traps", None),
    ("post", "/api/internal/honeypot/hit", {}),
    ("get", "/api/internal/rate-limits", None),
    ("post", "/api/internal/auth-wall/validate-session", {"session_id": "a", "auth_wall_id": "b", "signature": "c"}),
    ("get", "/api/internal/auth-wall/some-wall/config", None),
    ("post", "/api/internal/auth-wall/update-activity", {"session_id": "a"}),
    ("post", "/api/internal/push/send", {"title": "t", "body": "b"}),
    ("post", "/api/internal/admin-mfa/verify", {}),
]


class TestInternalRoutesNeedToken:
    @pytest.mark.parametrize("method,path,body", INTERNAL_ROUTES)
    async def test_no_token_refused(self, client, method, path, body):
        kwargs = {"json": body} if body is not None else {}
        r = await getattr(client, method)(path, **kwargs)
        assert r.status_code == 401, (path, r.status_code)

    @pytest.mark.parametrize("method,path,body", INTERNAL_ROUTES)
    async def test_wrong_token_refused(self, client, method, path, body):
        kwargs = {"json": body} if body is not None else {}
        r = await getattr(client, method)(path, headers={"X-Internal-Auth": "nope"}, **kwargs)
        assert r.status_code == 401, (path, r.status_code)

    async def test_right_token_accepted(self, client):
        r = await client.post(
            "/api/internal/auth-wall/validate-session",
            json={"session_id": "a", "auth_wall_id": "b", "signature": "c"},
            headers={"X-Internal-Auth": "test-internal-token"},
        )
        assert r.status_code == 200
        assert r.json()["valid"] is False


# ── client address ───────────────────────────────────────────────────────

class TestTrustedProxies:
    def proxies(self):
        return TrustedProxies("127.0.0.1,10.9.0.0/16,edge", resolver=lambda name: ["172.30.0.5"] if name == "edge" else [])

    def test_untrusted_peer_headers_ignored(self):
        p = self.proxies()
        assert p.client_ip("203.0.113.9", "1.2.3.4", "5.6.7.8") == "203.0.113.9"

    def test_trusted_peer_rightmost_untrusted_hop(self):
        p = self.proxies()
        # client sent a fake X-Forwarded-For; the proxy appended the real address
        assert p.client_ip("172.30.0.5", "1.2.3.4, 198.51.100.7") == "198.51.100.7"
        assert p.client_ip("10.9.1.1", "198.51.100.7, 10.9.2.2") == "198.51.100.7"

    def test_trusted_peer_real_ip_when_no_xff(self):
        assert self.proxies().client_ip("127.0.0.1", None, "198.51.100.7") == "198.51.100.7"

    def test_ipv4_mapped_peer(self):
        assert self.proxies().client_ip("::ffff:203.0.113.9", "1.2.3.4") == "203.0.113.9"

    def test_garbage_hop_stops_the_walk(self):
        assert self.proxies().client_ip("127.0.0.1", "1.2.3.4, nonsense, 10.9.0.1") == "10.9.0.1"

    def test_empty_env_means_default(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXIES", "")
        assert "ghostwire-proxy-nginx" in TrustedProxies().spec


class TestMiddleware:
    async def _client_seen(self, peer, headers, proxies):
        seen = {}

        async def app(scope, receive, send):
            seen["client"] = scope["client"][0]
            seen["scheme"] = scope["scheme"]
            await send({"type": "http.response.start", "status": 204, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        transport = ASGITransport(app=TrustedProxyMiddleware(app, proxies), client=(peer, 1234))
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            await c.get("/", headers=headers)
        return seen

    async def test_spoofed_headers_from_outside(self):
        seen = await self._client_seen(
            "203.0.113.9", {"X-Forwarded-For": "1.1.1.1", "X-Forwarded-Proto": "https"},
            TrustedProxies("127.0.0.1"),
        )
        assert seen == {"client": "203.0.113.9", "scheme": "http"}

    async def test_headers_from_trusted_proxy(self):
        seen = await self._client_seen(
            "127.0.0.1", {"X-Forwarded-For": "1.1.1.1, 198.51.100.7", "X-Forwarded-Proto": "https"},
            TrustedProxies("127.0.0.1"),
        )
        assert seen == {"client": "198.51.100.7", "scheme": "https"}


class TestMfaRateLimitNotBypassedBySpoofing:
    async def test_rotating_xff_from_untrusted_peer_shares_one_bucket(self, auth_headers):
        """Five allowed per minute: rotating X-Forwarded-For must not reset the count."""
        from app.core.client_ip import reset_trusted_proxies
        from app.core.database import get_db
        from app.core.rate_limiter import limiter
        from app.main import app
        from tests.conftest import _override_get_db

        reset_trusted_proxies("127.0.0.1")
        limiter.reset()
        app.dependency_overrides[get_db] = _override_get_db
        try:
            transport = ASGITransport(app=app, client=("203.0.113.50", 4000))
            codes = []
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                for i in range(8):
                    r = await c.post(
                        "/api/admin-mfa/verify",
                        json={"code": "000000"},
                        headers={**auth_headers, "X-Forwarded-For": f"10.0.0.{i}", "X-Real-IP": f"10.1.0.{i}"},
                    )
                    codes.append(r.status_code)
            assert 429 in codes, codes
        finally:
            app.dependency_overrides.clear()
            reset_trusted_proxies(None)
            limiter.reset()


# ── settings ─────────────────────────────────────────────────────────────

class TestSecretSettings:
    async def _store(self, db_session, key, value):
        db_session.add(Setting(key=key, value=value))
        await db_session.commit()

    async def test_non_admin_sees_mask(self, client, db_session, user_auth_headers):
        await self._store(db_session, "abuseipdb_api_key", "abcdef0123456789secretWXYZ")
        r = await client.get("/api/settings/abuseipdb_api_key", headers=user_auth_headers)
        assert r.status_code == 200
        assert r.json()["value"] == "••••WXYZ"
        r = await client.get("/api/settings/", headers=user_auth_headers)
        values = {s["key"]: s["value"] for s in r.json()}
        assert "secret" not in values["abuseipdb_api_key"]

    async def test_admin_sees_mask_too(self, client, db_session, auth_headers):
        await self._store(db_session, "smtp_password", "gAAAAAciphertext")
        r = await client.get("/api/settings/", headers=auth_headers)
        values = {s["key"]: s["value"] for s in r.json()}
        assert values["smtp_password"] == "••••"

    async def test_masked_value_written_back_keeps_secret(self, client, db_session, auth_headers):
        await self._store(db_session, "abuseipdb_api_key", "abcdef0123456789secretWXYZ")
        r = await client.put("/api/settings/", headers=auth_headers,
                             json={"settings": {"abuseipdb_api_key": "••••WXYZ", "letsencrypt_email": "a@b.co"}})
        assert r.status_code == 200
        r = await client.put("/api/settings/abuseipdb_api_key", headers=auth_headers, json={"value": "••••WXYZ"})
        assert r.status_code == 200
        db_session.expire_all()
        stored = (await db_session.execute(select(Setting.value).where(Setting.key == "abuseipdb_api_key"))).scalar_one()
        assert stored == "abcdef0123456789secretWXYZ"

    async def test_new_value_replaces_secret(self, client, db_session, auth_headers):
        await self._store(db_session, "abuseipdb_api_key", "old-old-old-old-old")
        r = await client.put("/api/settings/abuseipdb_api_key", headers=auth_headers, json={"value": "new-key-1234567890"})
        assert r.json()["value"] == "••••7890"
        db_session.expire_all()
        stored = (await db_session.execute(select(Setting.value).where(Setting.key == "abuseipdb_api_key"))).scalar_one()
        assert stored == "new-key-1234567890"


# ── alert channels ───────────────────────────────────────────────────────

async def _public(name):
    return ["93.184.216.34"]


class TestOutboundUrl:
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/hook", "http://10.0.0.5/", "http://192.168.1.1:8080/x",
        "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://[fd00::1]/",
        "http://localhost/", "http://100.64.0.1/", "http://0.0.0.0/",
    ])
    async def test_internal_refused(self, url):
        with pytest.raises(OutboundUrlError):
            await validate_outbound_url(url, resolver=_public)

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "gopher://x/", "ftp://example.com/", "https:///nohost", ""])
    async def test_bad_scheme_or_host(self, url):
        with pytest.raises(OutboundUrlError):
            await validate_outbound_url(url, resolver=_public)

    async def test_name_resolving_inside_refused(self):
        with pytest.raises(OutboundUrlError):
            await validate_outbound_url("https://hooks.example.com/x", resolver=lambda n: _coro(["10.1.2.3"]))

    async def test_public_allowed(self):
        await validate_outbound_url("https://hooks.example.com/x", resolver=lambda n: _coro(["93.184.216.34"]))

    async def test_allow_internal_switch(self):
        await validate_outbound_url("http://10.0.0.5/hook", allow_internal=True)


async def _coro(value):
    return value


class TestAlertChannels:
    async def test_non_admin_cannot_create_or_test(self, client, user_auth_headers):
        r = await client.post("/api/alerts/channels", headers=user_auth_headers,
                              json={"channel_type": "webhook", "name": "x", "config": json.dumps({"url": "https://example.com"})})
        assert r.status_code == 403
        r = await client.post("/api/alerts/test", headers=user_auth_headers)
        assert r.status_code == 403
        r = await client.put("/api/alerts/channels/whatever", headers=user_auth_headers, json={"name": "y"})
        assert r.status_code == 403

    async def test_admin_internal_webhook_refused(self, client, auth_headers):
        r = await client.post("/api/alerts/channels", headers=auth_headers,
                              json={"channel_type": "webhook", "name": "x",
                                    "config": json.dumps({"url": "http://169.254.169.254/latest/"})})
        assert r.status_code == 422

    async def test_admin_internal_webhook_allowed_with_setting(self, client, db_session, auth_headers):
        db_session.add(Setting(key="alerts_allow_internal_webhooks", value="true"))
        await db_session.commit()
        r = await client.post("/api/alerts/channels", headers=auth_headers,
                              json={"channel_type": "webhook", "name": "lan",
                                    "config": json.dumps({"url": "http://192.168.1.20/hook"})})
        assert r.status_code == 201


# ── auth portal redirects ────────────────────────────────────────────────

class TestRedirectTargets:
    @pytest.mark.parametrize("target", [
        "/", "/admin", "/a/b?x=1#frag", "https://app.example.test/x", "http://app.example.test:8443/y",
    ])
    def test_same_site_allowed(self, target):
        assert is_safe_redirect(target, "app.example.test")

    @pytest.mark.parametrize("target", [
        "javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,x", "//evil.example/x",
        "/\\evil.example", "https://evil.example/", "https://app.example.test.evil.example/",
        "https://user:pw@app.example.test/", " /x", "/x\n", "\t/x", "vbscript:x", "",
    ])
    def test_others_refused(self, target):
        assert not is_safe_redirect(target, "app.example.test")

    async def test_oauth_start_never_stores_offsite_redirect(self, client, db_session):
        from app.models.auth_wall import AuthProvider, AuthWall
        from app.core.security import encrypt_data

        wall = AuthWall(name="W", auth_type="oauth")
        db_session.add(wall)
        await db_session.flush()
        provider = AuthProvider(auth_wall_id=wall.id, name="G", provider_type="google",
                                client_id="cid", client_secret=encrypt_data("s"), enabled=True)
        db_session.add(provider)
        await db_session.commit()

        stored = {}

        async def fake_set(state, data, ttl_seconds=600):
            stored.update(data)

        with patch("app.api.routes.auth_portal._set_oauth_state", fake_set):
            r = await client.get(
                f"/api/auth-portal/{wall.id}/oauth/{provider.id}/start",
                params={"redirect": "javascript:alert(document.cookie)"},
                headers={"Host": "app.example.test"},
            )
        assert r.status_code == 302
        assert r.headers["location"].startswith("https://accounts.google.com/")
        assert stored["redirect_url"] == "/"
        assert stored["callback_url"].endswith(f"app.example.test/api/auth-portal/{wall.id}/callback")
        assert "redirect_uri=http" in r.headers["location"]


# ── OAuth allow-list ─────────────────────────────────────────────────────

def _wall(emails=None, domains=None, providers=()):
    return SimpleNamespace(allowed_emails=emails or [], allowed_email_domains=domains or [], auth_providers=list(providers))


class TestAllowList:
    def test_empty_list_keeps_previous_behaviour(self):
        assert is_email_allowed(_wall(), "anyone@gmail.com")

    def test_exact_email(self):
        w = _wall(emails=["alice@example.com"])
        assert is_email_allowed(w, "Alice@Example.com")
        assert not is_email_allowed(w, "bob@example.com")

    def test_domain(self):
        w = _wall(domains=["example.com"])
        assert is_email_allowed(w, "bob@example.com")
        assert not is_email_allowed(w, "bob@sub.example.com")
        assert not is_email_allowed(w, "bob@example.com.evil.io")
        assert not is_email_allowed(w, "bob@notexample.com")

    def test_missing_or_bad_email_refused_when_listed(self):
        w = _wall(domains=["example.com"])
        assert not is_email_allowed(w, None)
        assert not is_email_allowed(w, "")
        assert not is_email_allowed(w, "example.com")

    def test_open_to_any_account(self):
        google = SimpleNamespace(provider_type="google", enabled=True)
        off = SimpleNamespace(provider_type="github", enabled=False)
        assert open_to_any_account(_wall(providers=[google]))
        assert not open_to_any_account(_wall(providers=[off]))
        assert not open_to_any_account(_wall(domains=["example.com"], providers=[google]))
        assert not open_to_any_account(_wall())

    def test_normalisers(self):
        assert normalize_email(" A@B.CO ") == "a@b.co"
        assert normalize_domain("@Example.COM") == "example.com"
        assert clean_list(["a@b.co", "A@b.co", " "], normalize_email) == ["a@b.co"]
        with pytest.raises(ValueError):
            normalize_domain("exa mple.com")
        with pytest.raises(ValueError):
            normalize_email("not-an-email")


class TestAllowListApi:
    async def test_create_update_and_warning_flag(self, client, auth_headers):
        r = await client.post("/api/auth-walls/", headers=auth_headers, json={
            "name": "Staff", "auth_type": "oauth",
            "auth_providers": [{"name": "Google", "provider_type": "google", "client_id": "c", "client_secret": "s"}],
        })
        assert r.status_code == 201, r.text
        wall = r.json()
        assert wall["oauth_open_to_anyone"] is True
        assert wall["allowed_emails"] == [] and wall["allowed_email_domains"] == []

        r = await client.put(f"/api/auth-walls/{wall['id']}", headers=auth_headers,
                             json={"allowed_email_domains": ["Example.com", "example.com"], "allowed_emails": ["Boss@Other.org"]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["allowed_email_domains"] == ["example.com"]
        assert body["allowed_emails"] == ["boss@other.org"]
        assert body["oauth_open_to_anyone"] is False

    async def test_invalid_entries_rejected(self, client, auth_headers):
        r = await client.post("/api/auth-walls/", headers=auth_headers,
                              json={"name": "X", "allowed_email_domains": ["not a domain"]})
        assert r.status_code == 422

    @pytest.mark.parametrize("name", ['a"b', "a;b", "a{b", "a\nb", "$host"])
    async def test_name_cannot_break_config(self, client, auth_headers, name):
        r = await client.post("/api/auth-walls/", headers=auth_headers, json={"name": name})
        assert r.status_code == 422

    async def test_theme_must_be_a_directory_name(self, client, auth_headers):
        r = await client.post("/api/auth-walls/", headers=auth_headers, json={"name": "X", "theme": "../../etc"})
        assert r.status_code == 422


class TestOAuthCallbackEnforcesAllowList:
    async def _setup(self, db_session, domains):
        from app.core.security import encrypt_data
        from app.models.auth_wall import AuthProvider, AuthWall

        wall = AuthWall(name="W", auth_type="oauth", allowed_email_domains=domains, allowed_emails=[])
        db_session.add(wall)
        await db_session.flush()
        provider = AuthProvider(auth_wall_id=wall.id, name="G", provider_type="google",
                                client_id="cid", client_secret=encrypt_data("s"), enabled=True)
        db_session.add(provider)
        await db_session.commit()
        return wall, provider

    async def _callback(self, client, wall, provider, email):
        from datetime import datetime, timedelta, timezone
        from app.services.auth_providers.base import UserInfo

        state = {
            "auth_wall_id": wall.id, "provider_id": provider.id, "redirect_url": "/home",
            "callback_url": "https://app.example.test/cb",
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
        info = UserInfo(user_id="1", username="u", email=email, provider_type="google",
                        raw_data={"email_verified": True})
        with patch("app.api.routes.auth_portal._get_oauth_state", AsyncMock(return_value=state)), \
             patch("app.api.routes.auth_portal._del_oauth_state", AsyncMock()), \
             patch("app.services.auth_providers.google.GoogleAuthProvider.handle_callback", AsyncMock(return_value=info)):
            return await client.get(f"/api/auth-portal/{wall.id}/callback",
                                    params={"code": "c", "state": "s"}, headers={"Host": "app.example.test"})

    async def test_outsider_refused(self, client, db_session):
        wall, provider = await self._setup(db_session, ["example.com"])
        r = await self._callback(client, wall, provider, "mallory@gmail.com")
        assert r.status_code == 302
        assert r.headers["location"].startswith("/__auth/callback?")
        assert "error=" in r.headers["location"]
        assert "set-cookie" not in r.headers

    async def test_listed_domain_admitted(self, client, db_session):
        wall, provider = await self._setup(db_session, ["example.com"])
        with patch("app.services.session_service.SessionService.create_session",
                   AsyncMock(return_value=(SimpleNamespace(id="s"), "sid.sig"))):
            r = await self._callback(client, wall, provider, "alice@example.com")
        assert r.status_code == 302
        assert r.headers["location"] == "/home"
        assert "set-cookie" in r.headers


# ── backups ──────────────────────────────────────────────────────────────

class TestBackupSafety:
    async def test_without_traffic_logs_keeps_the_table(self, tmp_path):
        from app.services.backup_service import BackupService

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            dump = cmd[cmd.index("-f") + 1]
            open(dump, "wb").write(b"PGDMP")
            return SimpleNamespace(returncode=0, stderr="", stdout="")

        with patch("app.services.backup_service.subprocess.run", fake_run):
            await BackupService()._backup_database(str(tmp_path), include_traffic_logs=False)
        assert "--exclude-table-data=traffic_logs" in calls[0]
        assert "--exclude-table=traffic_logs" not in calls[0]

    async def test_restore_errors_are_failures(self, tmp_path):
        from app.services.backup_service import BackupService

        (tmp_path / "database").mkdir()
        (tmp_path / "database" / "ghostwire_proxy.dump").write_bytes(b"PGDMP")

        def fake_run(cmd, **kwargs):
            if cmd[0] == "pg_restore":
                return SimpleNamespace(returncode=1, stdout="",
                                       stderr="pg_restore: error: could not execute query: ERROR:  relation \"x\" does not exist\n"
                                              "pg_restore: warning: errors ignored on restore: 1\n")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with patch("app.services.backup_service.subprocess.run", fake_run):
            with pytest.raises(RuntimeError, match="statements failed"):
                await BackupService()._restore_database(str(tmp_path))

    async def test_failed_database_restore_is_not_reported_as_success(self, tmp_path, db_session):
        import tarfile

        from app.models.backup import Backup
        from app.services.backup_service import BackupService

        src = tmp_path / "src"
        (src / "database").mkdir(parents=True)
        (src / "database" / "ghostwire_proxy.dump").write_bytes(b"PGDMP")
        archive = tmp_path / "b.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(src / "database", arcname="database")

        backup = Backup(filename="b.tar.gz", file_path=str(archive), status="completed",
                        includes_database=True, includes_certificates=True,
                        includes_letsencrypt=False, includes_configs=False, backup_type="manual")
        db_session.add(backup)
        await db_session.commit()

        service = BackupService()
        service._restore_certificates = MagicMock()
        with patch.object(service, "_restore_database", AsyncMock(side_effect=RuntimeError("boom"))):
            with pytest.raises(RuntimeError, match="nothing else was restored"):
                await service.restore_backup(db_session, backup.id)
        service._restore_certificates.assert_not_called()
