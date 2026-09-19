"""Internal two-factor endpoints the admin UI's sign-in (Better Auth plugin) calls."""

import pyotp
import pytest

from app.core.security import decrypt_data
from app.models.user import User
from app.services import admin_mfa_service as mfa

INTERNAL = {"X-Internal-Auth": "test-internal-token"}
BASE = "/api/internal/admin-mfa"


@pytest.fixture
async def enrolled(db_session, admin_user: User):
    setup = await mfa.begin_enrolment(db_session, admin_user)
    assert await mfa.confirm_enrolment(db_session, admin_user, pyotp.TOTP(setup["secret"]).now())
    return admin_user, setup


class TestInternalAuth:
    @pytest.mark.asyncio
    async def test_requires_internal_token(self, client, admin_user):
        response = await client.post(f"{BASE}/state", json={"user_id": admin_user.id})
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_wrong_token(self, client, admin_user):
        response = await client.post(
            f"{BASE}/state", json={"user_id": admin_user.id}, headers={"X-Internal-Auth": "nope"}
        )
        assert response.status_code == 401


class TestState:
    @pytest.mark.asyncio
    async def test_nothing_required_by_default(self, client, admin_user):
        response = await client.post(f"{BASE}/state", json={"user_id": admin_user.id}, headers=INTERNAL)
        assert response.json() == {"required": "none"}

    @pytest.mark.asyncio
    async def test_enrolled_user_needs_a_code(self, client, enrolled):
        user, _ = enrolled
        response = await client.post(f"{BASE}/state", json={"user_id": user.id}, headers=INTERNAL)
        assert response.json() == {"required": "totp"}

    @pytest.mark.asyncio
    async def test_policy_requires_enrolment(self, client, db_session, admin_user):
        await mfa.set_mfa_required(db_session, True)
        response = await client.post(f"{BASE}/state", json={"user_id": admin_user.id}, headers=INTERNAL)
        assert response.json() == {"required": "enrol"}

    @pytest.mark.asyncio
    async def test_disabled_user_refused(self, client, inactive_user):
        response = await client.post(f"{BASE}/state", json={"user_id": inactive_user.id}, headers=INTERNAL)
        assert response.status_code == 404


class TestVerify:
    @pytest.mark.asyncio
    async def test_valid_totp(self, client, enrolled):
        user, setup = enrolled
        response = await client.post(
            f"{BASE}/verify",
            json={"user_id": user.id, "code": pyotp.TOTP(setup["secret"]).now()},
            headers=INTERNAL,
        )
        assert response.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_wrong_code(self, client, enrolled):
        user, _ = enrolled
        response = await client.post(
            f"{BASE}/verify", json={"user_id": user.id, "code": "000000"}, headers=INTERNAL
        )
        assert response.json()["ok"] is False

    @pytest.mark.asyncio
    async def test_backup_code_works_once(self, client, enrolled):
        user, setup = enrolled
        code = setup["backup_codes"][0]
        first = await client.post(f"{BASE}/verify", json={"user_id": user.id, "code": code}, headers=INTERNAL)
        again = await client.post(f"{BASE}/verify", json={"user_id": user.id, "code": code}, headers=INTERNAL)
        assert first.json() == {"ok": True, "backup_codes_remaining": len(setup["backup_codes"]) - 1}
        assert again.json()["ok"] is False


class TestEnrolment:
    @pytest.mark.asyncio
    async def test_begin_then_confirm(self, client, db_session, admin_user):
        begun = await client.post(f"{BASE}/enrol/begin", json={"user_id": admin_user.id}, headers=INTERNAL)
        assert begun.status_code == 200
        secret = begun.json()["secret"]
        assert begun.json()["backup_codes"]

        confirmed = await client.post(
            f"{BASE}/enrol/confirm",
            json={"user_id": admin_user.id, "code": pyotp.TOTP(secret).now()},
            headers=INTERNAL,
        )
        assert confirmed.json() == {"ok": True}
        await db_session.refresh(admin_user)
        assert mfa.is_enrolled(admin_user)
        assert decrypt_data(admin_user.totp_secret) == secret

    @pytest.mark.asyncio
    async def test_wrong_code_does_not_enable(self, client, db_session, admin_user):
        await client.post(f"{BASE}/enrol/begin", json={"user_id": admin_user.id}, headers=INTERNAL)
        confirmed = await client.post(
            f"{BASE}/enrol/confirm", json={"user_id": admin_user.id, "code": "000000"}, headers=INTERNAL
        )
        assert confirmed.json() == {"ok": False}
        await db_session.refresh(admin_user)
        assert not mfa.is_enrolled(admin_user)

    @pytest.mark.asyncio
    async def test_cannot_replace_an_active_secret(self, client, enrolled):
        user, _ = enrolled
        response = await client.post(f"{BASE}/enrol/begin", json={"user_id": user.id}, headers=INTERNAL)
        assert response.status_code == 409


class TestSettingsRoutes:
    """The settings page's own two-factor routes, now under /api/admin-mfa with a session."""

    @pytest.mark.asyncio
    async def test_status_needs_session(self, client):
        assert (await client.get("/api/admin-mfa/status")).status_code == 401

    @pytest.mark.asyncio
    async def test_status_with_session(self, client, admin_user, auth_headers):
        response = await client.get("/api/admin-mfa/status", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["enabled"] is False

    @pytest.mark.asyncio
    async def test_disable_checks_the_sign_in_password(self, client, db_session, enrolled, auth_headers):
        user, setup = enrolled
        wrong = await client.post(
            "/api/admin-mfa/disable",
            json={"password": "not-it", "code": pyotp.TOTP(setup["secret"]).now()},
            headers=auth_headers,
        )
        assert wrong.status_code in (400, 401, 403)
        await db_session.refresh(user)
        assert mfa.is_enrolled(user)
