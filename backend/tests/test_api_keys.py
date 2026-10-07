"""Scoped API keys: minting, authentication, scope enforcement, revocation and audit."""
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from sqlalchemy import select

from app.core.rate_limiter import limiter
from app.core.security import encrypt_data
from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog
from app.services import api_key_service
from app.services.api_key_service import SESSION_ONLY, required_scope


@pytest.fixture(autouse=True)
def _reset_limits():
    limiter.reset()
    api_key_service.failed_attempts.reset()
    yield
    api_key_service.failed_attempts.reset()


@pytest.fixture
async def mfa_admin(db_session, admin_user):
    secret = pyotp.random_base32()
    admin_user.totp_secret = encrypt_data(secret)
    admin_user.totp_enabled = True
    admin_user.totp_verified = True
    await db_session.commit()
    return admin_user, secret


async def make_key(db_session, user, scopes, **kwargs):
    row, key = await api_key_service.create_key(db_session, user, kwargs.pop("name", "test"), scopes, kwargs.pop("days", None))
    for field, value in kwargs.items():
        setattr(row, field, value)
    await db_session.commit()
    return row, key


def bearer(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


class TestRequiredScope:
    @pytest.mark.parametrize("method,path,scope", [
        ("GET", "/api/proxy-hosts/", "read"),
        ("GET", "/api/proxy-hosts/abc", "read"),
        ("POST", "/api/proxy-hosts/", "write:proxy-hosts"),
        ("PUT", "/api/proxy-hosts/abc", "write:proxy-hosts"),
        ("POST", "/api/proxy-hosts/abc/enable", "write:proxy-hosts"),
        ("POST", "/api/proxy-hosts/abc/upstreams", "write:upstreams"),
        ("PATCH", "/api/proxy-hosts/abc/upstreams/def", "write:upstreams"),
        ("POST", "/api/proxy-hosts/upstream-preview", "read"),
        ("POST", "/api/config/preview", "read"),
        ("POST", "/api/config/reload", "write:nginx"),
        ("POST", "/api/settings/reload-nginx", "write:nginx"),
        ("POST", "/api/certificates/letsencrypt", "write:certificates"),
        ("PUT", "/api/access-lists/x", "write:access"),
        ("POST", "/api/auth-walls/x/users", "write:access"),
        ("POST", "/api/waf/rules", "write:security"),
        ("GET", "/api/traffic/stats", "read"),
        ("GET", "/api/audit-logs/", "read"),
        ("PUT", "/api/settings/x", "admin"),
        ("GET", "/api/settings/", "admin"),
        ("POST", "/api/dns/providers", "admin"),
        ("GET", "/api/updates/check/app", "admin"),
        ("GET", "/api/users/me", "read"),
        # Never through a key
        ("GET", "/api/users/", SESSION_ONLY),
        ("POST", "/api/users/", SESSION_ONLY),
        ("GET", "/api/api-keys/", SESSION_ONLY),
        ("POST", "/api/admin-mfa/disable", SESSION_ONLY),
        ("POST", "/api/updates/app", SESSION_ONLY),
        ("POST", "/api/updates/rollback/x", SESSION_ONLY),
        ("PUT", "/api/updates/settings", SESSION_ONLY),
        ("POST", "/api/containers/auto-update/run", SESSION_ONLY),
        ("POST", "/api/backups/restore", SESSION_ONLY),
        ("POST", "/api/backups/upload", SESSION_ONLY),
        ("GET", "/api/backups/x/download", SESSION_ONLY),
        ("POST", "/api/system/kill-switch", SESSION_ONLY),
        # Unlisted = refused
        ("GET", "/api/something-new", None),
    ])
    def test_mapping(self, method, path, scope):
        assert required_scope(method, path) == scope

    def test_admin_scope_covers_everything_but_session_only(self):
        assert api_key_service.has_scope(["admin"], "write:proxy-hosts")
        assert not api_key_service.has_scope(["read"], "write:proxy-hosts")

    def test_every_key_can_read(self):
        assert api_key_service.normalize_scopes(["write:upstreams"]) == ["read", "write:upstreams"]

    def test_unknown_scope_rejected(self):
        with pytest.raises(ValueError):
            api_key_service.normalize_scopes(["write:everything"])


class TestKeyFormat:
    def test_generated_key_shape(self):
        key, prefix = api_key_service.generate_key()
        assert key.startswith(f"gwp_{prefix}_")
        assert len(prefix) == 10
        assert len(key.split("_")[2]) == 40

    async def test_only_hash_is_stored(self, db_session, admin_user):
        row, key = await make_key(db_session, admin_user, ["read"])
        stored = (await db_session.execute(select(ApiKey).where(ApiKey.id == row.id))).scalar_one()
        assert stored.hash == api_key_service.hash_key(key)
        assert key not in (stored.hash, stored.prefix)
        assert key.split("_")[2] not in str(stored.__dict__)


class TestCreateEndpoint:
    async def test_requires_two_factor_enrolment(self, client, auth_headers):
        r = await client.post("/api/api-keys/", headers=auth_headers,
                              json={"name": "agent", "scopes": ["read"], "code": "123456"})
        assert r.status_code == 403
        assert "two-factor" in r.json()["detail"].lower()

    async def test_wrong_code_rejected(self, client, auth_headers, mfa_admin):
        r = await client.post("/api/api-keys/", headers=auth_headers,
                              json={"name": "agent", "scopes": ["read"], "code": "000000"})
        assert r.status_code == 400

    async def test_creates_key_shown_once(self, client, auth_headers, mfa_admin, db_session):
        _, secret = mfa_admin
        r = await client.post("/api/api-keys/", headers=auth_headers, json={
            "name": "Claude Code", "scopes": ["write:proxy-hosts"], "expires_in_days": 30,
            "code": pyotp.TOTP(secret).now(),
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["key"].startswith(f"gwp_{body['prefix']}_")
        assert body["scopes"] == ["read", "write:proxy-hosts"]
        assert body["status"] == "active"
        assert body["expires_at"] is not None

        listed = (await client.get("/api/api-keys/", headers=auth_headers)).json()
        assert [k["id"] for k in listed] == [body["id"]]
        assert "key" not in listed[0]

        audit = (await db_session.execute(select(AuditLog).where(AuditLog.action == "api_key_created"))).scalars().all()
        assert len(audit) == 1 and body["key"] not in audit[0].details

    async def test_regular_user_cannot_create(self, client, user_auth_headers):
        r = await client.post("/api/api-keys/", headers=user_auth_headers,
                              json={"name": "x", "scopes": ["read"], "code": "123456"})
        assert r.status_code == 403

    async def test_keys_cannot_manage_keys(self, client, db_session, admin_user):
        _, key = await make_key(db_session, admin_user, ["admin"])
        assert (await client.get("/api/api-keys/", headers=bearer(key))).status_code == 403
        r = await client.post("/api/api-keys/", headers=bearer(key),
                              json={"name": "x", "scopes": ["admin"], "code": "123456"})
        assert r.status_code == 403


class TestKeyAuthentication:
    async def test_read_key_can_read(self, client, db_session, admin_user):
        _, key = await make_key(db_session, admin_user, ["read"])
        r = await client.get("/api/proxy-hosts/", headers=bearer(key))
        assert r.status_code == 200

    async def test_read_key_cannot_mutate(self, client, db_session, admin_user):
        _, key = await make_key(db_session, admin_user, ["read"])
        r = await client.post("/api/proxy-hosts/", headers=bearer(key), json={
            "domain_names": ["a.example.com"], "forward_host": "10.0.0.1", "forward_port": 80,
        })
        assert r.status_code == 403
        assert "write:proxy-hosts" in r.json()["detail"]

    async def test_session_only_routes_refuse_admin_key(self, client, db_session, admin_user):
        _, key = await make_key(db_session, admin_user, ["admin"])
        for method, path in [("GET", "/api/users/"), ("POST", "/api/backups/restore"),
                             ("POST", "/api/updates/app"), ("GET", "/api/admin-mfa/status")]:
            r = await client.request(method, path, headers=bearer(key))
            assert r.status_code == 403, (method, path, r.status_code)
            assert "not available to API keys" in r.json()["detail"]

    async def test_admin_key_reaches_admin_routes(self, client, db_session, admin_user):
        _, key = await make_key(db_session, admin_user, ["admin"])
        assert (await client.get("/api/settings/", headers=bearer(key))).status_code == 200

    async def test_read_key_refused_on_admin_routes(self, client, db_session, admin_user):
        _, key = await make_key(db_session, admin_user, ["read"])
        assert (await client.get("/api/settings/", headers=bearer(key))).status_code == 403

    async def test_revoked_key_rejected(self, client, db_session, admin_user):
        _, key = await make_key(db_session, admin_user, ["read"], revoked_at=datetime.now(timezone.utc))
        r = await client.get("/api/proxy-hosts/", headers=bearer(key))
        assert r.status_code == 401
        assert "revoked" in r.json()["detail"]

    async def test_expired_key_rejected(self, client, db_session, admin_user):
        _, key = await make_key(db_session, admin_user, ["read"],
                                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        r = await client.get("/api/proxy-hosts/", headers=bearer(key))
        assert r.status_code == 401
        assert "expired" in r.json()["detail"]

    async def test_wrong_secret_rejected(self, client, db_session, admin_user):
        row, key = await make_key(db_session, admin_user, ["read"])
        forged = f"gwp_{row.prefix}_" + "A" * 40
        assert (await client.get("/api/proxy-hosts/", headers=bearer(forged))).status_code == 401

    async def test_malformed_key_rejected(self, client):
        assert (await client.get("/api/proxy-hosts/", headers=bearer("gwp_nope"))).status_code == 401

    async def test_failed_attempts_are_throttled(self, client, db_session, admin_user):
        _, good = await make_key(db_session, admin_user, ["read"])
        for _ in range(api_key_service.failed_attempts.max_failures):
            await client.get("/api/proxy-hosts/", headers=bearer("gwp_" + "x" * 10 + "_" + "y" * 40))
        r = await client.get("/api/proxy-hosts/", headers=bearer(good))
        assert r.status_code == 429

    async def test_key_stops_when_creator_disabled_or_demoted(self, client, db_session, admin_user):
        _, key = await make_key(db_session, admin_user, ["read"])
        admin_user.role = "user"
        await db_session.commit()
        assert (await client.get("/api/proxy-hosts/", headers=bearer(key))).status_code == 403
        admin_user.role = "admin"
        admin_user.is_active = False
        await db_session.commit()
        assert (await client.get("/api/proxy-hosts/", headers=bearer(key))).status_code == 401

    async def test_last_used_recorded(self, client, db_session, admin_user):
        row, key = await make_key(db_session, admin_user, ["read"])
        await client.get("/api/proxy-hosts/", headers={**bearer(key), "X-Forwarded-For": "203.0.113.9"})
        await db_session.refresh(row)
        assert row.last_used_at is not None
        assert row.last_used_ip == "203.0.113.9"

    async def test_mutation_with_key_is_audited(self, client, db_session, admin_user):
        _, key = await make_key(db_session, admin_user, ["write:proxy-hosts"], name="agent")
        # Invalid body: the request fails, but the attempt is still on record.
        await client.post("/api/proxy-hosts/", headers=bearer(key), json={})
        rows = (await db_session.execute(select(AuditLog).where(AuditLog.action == "api_key_used"))).scalars().all()
        assert len(rows) == 1
        assert "agent" in rows[0].details and "POST /api/proxy-hosts/" in rows[0].details
        assert key not in rows[0].details

    async def test_session_auth_unchanged(self, client, auth_headers):
        assert (await client.get("/api/users/", headers=auth_headers)).status_code == 200


class TestRevoke:
    async def test_revoke_soft_deletes(self, client, auth_headers, db_session, admin_user):
        row, key = await make_key(db_session, admin_user, ["read"])
        r = await client.delete(f"/api/api-keys/{row.id}", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "revoked"
        assert (await client.get("/api/proxy-hosts/", headers=bearer(key))).status_code == 401
        await db_session.refresh(row)
        assert row.revoked_at is not None
