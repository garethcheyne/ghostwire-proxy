"""Tests for auth wall API routes: anyone signed in can view, only admins can change."""

import secrets

import pytest

from app.models.auth_wall import AuthWall


@pytest.fixture
async def wall(db_session):
    wall = AuthWall(name="Staff", auth_type="basic", session_timeout=3600)
    db_session.add(wall)
    await db_session.commit()
    await db_session.refresh(wall)
    return wall


class TestAuthWallPermissions:

    @pytest.mark.asyncio
    async def test_regular_user_can_list(self, client, regular_user, user_auth_headers, wall):
        response = await client.get("/api/auth-walls/", headers=user_auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_regular_user_cannot_create(self, client, regular_user, user_auth_headers):
        response = await client.post("/api/auth-walls/", headers=user_auth_headers, json={
            "name": "Sneaky", "auth_type": "basic",
        })
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_regular_user_cannot_update(self, client, regular_user, user_auth_headers, wall):
        response = await client.put(f"/api/auth-walls/{wall.id}", headers=user_auth_headers, json={"name": "Renamed"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_regular_user_cannot_delete(self, client, regular_user, user_auth_headers, wall):
        response = await client.delete(f"/api/auth-walls/{wall.id}", headers=user_auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_regular_user_cannot_add_login(self, client, regular_user, user_auth_headers, wall):
        response = await client.post(f"/api/auth-walls/{wall.id}/users", headers=user_auth_headers, json={
            "username": "me", "password": secrets.token_urlsafe(16),
        })
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_create(self, client, admin_user, auth_headers):
        response = await client.post("/api/auth-walls/", headers=auth_headers, json={
            "name": "Staff only", "auth_type": "basic",
        })
        assert response.status_code == 201
        assert response.json()["proxy_hosts"] == []
