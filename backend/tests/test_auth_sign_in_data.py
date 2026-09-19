"""Passwords and sessions for admin sign-in live in Better Auth's tables."""

import pytest
from sqlalchemy import select

from app.core.security import verify_password
from app.models.auth import AuthAccount
from app.models.user import User


class TestUserManagement:
    @pytest.mark.asyncio
    async def test_create_user_gets_credential_account(self, client, admin_user, auth_headers, db_session):
        response = await client.post("/api/users/", headers=auth_headers, json={
            "email": "new@test.com", "name": "New", "password": "securepassword123", "role": "user",
        })
        assert response.status_code == 201
        user_id = response.json()["id"]

        account = (await db_session.execute(
            select(AuthAccount).where(AuthAccount.user_id == user_id)
        )).scalar_one()
        assert account.provider_id == "credential"
        assert account.account_id == user_id
        assert verify_password("securepassword123", account.password)

    @pytest.mark.asyncio
    async def test_password_change_updates_credential_and_signs_out(
        self, client, admin_user, regular_user, auth_headers, user_auth_headers, db_session
    ):
        assert (await client.get("/api/users/me", headers=user_auth_headers)).status_code == 200

        response = await client.put(
            f"/api/users/{regular_user.id}", headers=auth_headers, json={"password": "brandnewpass123"}
        )
        assert response.status_code == 200

        account = (await db_session.execute(
            select(AuthAccount).where(AuthAccount.user_id == regular_user.id)
        )).scalar_one()
        assert verify_password("brandnewpass123", account.password)
        assert (await client.get("/api/users/me", headers=user_auth_headers)).status_code == 401

    @pytest.mark.asyncio
    async def test_disabling_revokes_sessions(self, client, admin_user, regular_user, auth_headers, user_auth_headers):
        response = await client.put(
            f"/api/users/{regular_user.id}", headers=auth_headers, json={"is_active": False}
        )
        assert response.status_code == 200
        assert (await client.get("/api/users/me", headers=user_auth_headers)).status_code == 401

    @pytest.mark.asyncio
    async def test_deleting_removes_sign_in_data(self, client, admin_user, auth_headers, db_session):
        created = await client.post("/api/users/", headers=auth_headers, json={
            "email": "gone@test.com", "name": "Gone", "password": "securepassword123", "role": "user",
        })
        user_id = created.json()["id"]

        assert (await client.delete(f"/api/users/{user_id}", headers=auth_headers)).status_code == 204
        remaining = (await db_session.execute(
            select(AuthAccount).where(AuthAccount.user_id == user_id)
        )).scalars().all()
        assert remaining == []

    @pytest.mark.asyncio
    async def test_me(self, client, admin_user, auth_headers):
        response = await client.get("/api/users/me", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["email"] == "admin@test.com"

    @pytest.mark.asyncio
    async def test_me_requires_sign_in(self, client):
        assert (await client.get("/api/users/me")).status_code == 401


class TestSetup:
    @pytest.mark.asyncio
    async def test_initialize_creates_admin_with_credential(self, client, db_session):
        assert (await client.get("/api/setup/check")).json()["setup_required"] is True

        response = await client.post("/api/setup/initialize", json={
            "email": "First@Example.com", "password": "firstpassword1", "name": "First",
        })
        assert response.status_code == 200

        user = (await db_session.execute(select(User))).scalar_one()
        assert user.email == "first@example.com" and user.role == "admin"
        account = (await db_session.execute(select(AuthAccount))).scalar_one()
        assert account.user_id == user.id
        assert verify_password("firstpassword1", account.password)

        again = await client.post("/api/setup/initialize", json={
            "email": "second@example.com", "password": "secondpassword1", "name": "Second",
        })
        assert again.status_code == 400
