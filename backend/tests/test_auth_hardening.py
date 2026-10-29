"""Authorization and auth-wall sign-in hardening.

Admin-only actions, the last active admin, per-address limits on auth-wall
sign-in, wrong TOTP codes counting towards the lockout, and one use per code.
"""

from app.models.alert import AlertChannel
from sqlalchemy import select


class TestAdminOnlyActions:
    async def test_non_admin_cannot_delete_a_global_channel(self, client, db_session, user_auth_headers):
        channel = AlertChannel(user_id=None, channel_type="webhook", name="Global", config="{}")
        db_session.add(channel)
        await db_session.commit()
        channel_id = channel.id
        r = await client.delete(f"/api/alerts/channels/{channel_id}", headers=user_auth_headers)
        assert r.status_code == 403
        db_session.expire_all()
        assert (await db_session.execute(select(AlertChannel).where(AlertChannel.id == channel_id))).scalar()

    async def test_non_admin_cannot_run_enrichment_backfill(self, client, user_auth_headers):
        r = await client.post("/api/traffic/enrichment/backfill", headers=user_auth_headers)
        assert r.status_code == 403

    async def test_non_admin_cannot_force_an_enrichment_lookup(self, client, user_auth_headers):
        r = await client.get("/api/honeypot/enrich/1.2.3.4?force=true", headers=user_auth_headers)
        assert r.status_code == 403


class TestLastAdmin:
    async def test_only_admin_cannot_demote_or_disable_themselves(self, client, admin_user, auth_headers):
        r = await client.put(f"/api/users/{admin_user.id}", headers=auth_headers, json={"role": "user"})
        assert r.status_code == 400
        assert "only active admin" in r.json()["detail"]
        r = await client.put(f"/api/users/{admin_user.id}", headers=auth_headers, json={"is_active": False})
        assert r.status_code == 400

    async def test_allowed_when_another_admin_remains(self, client, db_session, admin_user, regular_user, auth_headers):
        regular_user.role = "admin"
        await db_session.commit()
        r = await client.put(f"/api/users/{regular_user.id}", headers=auth_headers, json={"role": "user"})
        assert r.status_code == 200


class TestTotpReplay:
    async def test_a_code_is_accepted_once_per_purpose(self):
        import uuid

        from app.services.totp_replay import claim_totp_code

        user_id = str(uuid.uuid4())
        assert await claim_totp_code("admin-login", user_id, "123456") is True
        assert await claim_totp_code("admin-login", user_id, "123456") is False
        assert await claim_totp_code("admin-disable", user_id, "123456") is True
        assert await claim_totp_code("admin-login", user_id, "654321") is True


class TestWallTotpLockout:
    async def _wall_user(self, db_session):
        import pyotp
        from app.core.security import encrypt_data, get_password_hash
        from app.models.auth_wall import AuthWall, LocalAuthUser

        wall = AuthWall(name="Staff", auth_type="local", session_timeout=3600)
        db_session.add(wall)
        await db_session.flush()
        secret = pyotp.random_base32()
        user = LocalAuthUser(
            auth_wall_id=wall.id,
            username="alice",
            password_hash=get_password_hash("correct-horse"),
            totp_enabled=True,
            totp_verified=True,
            totp_secret=encrypt_data(secret),
        )
        db_session.add(user)
        await db_session.commit()
        return wall, user, secret

    async def test_wrong_codes_lock_the_account_and_a_password_does_not_clear_them(self, db_session):
        from app.services.auth_providers.local import LocalAuthProvider

        wall, user, _secret = await self._wall_user(db_session)
        provider = LocalAuthProvider(auth_wall=wall, db=db_session)
        for _ in range(3):
            assert await provider.authenticate({"username": "alice", "password": "correct-horse"})
            assert not await provider.verify_totp(user, "000000")
            await db_session.refresh(user)
        # The right password in between did not wipe the wrong codes out.
        assert user.failed_attempts == 3
        for _ in range(2):
            assert not await provider.verify_totp(user, "000000")
            await db_session.refresh(user)
        assert user.is_locked()
        assert await provider.authenticate({"username": "alice", "password": "correct-horse"}) is None

    async def test_a_code_works_once(self, db_session):
        import pyotp
        from app.services.auth_providers.local import LocalAuthProvider

        wall, user, secret = await self._wall_user(db_session)
        provider = LocalAuthProvider(auth_wall=wall, db=db_session)
        code = pyotp.TOTP(secret).now()
        assert await provider.verify_totp(user, code)
        await db_session.refresh(user)
        assert not await provider.verify_totp(user, code)


class TestPortalLoginRateLimit:
    async def test_password_guessing_from_one_address_is_throttled(self, client):
        statuses = []
        for _ in range(12):
            r = await client.post("/api/auth-portal/no-such-wall/login/local", json={"username": "a", "password": "b"})
            statuses.append(r.status_code)
        assert 429 in statuses
        assert statuses[:10] == [404] * 10  # no such wall, but every attempt counts
