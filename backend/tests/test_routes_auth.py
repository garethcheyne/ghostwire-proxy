"""Tests for auth API routes — login, refresh, me."""

import pytest
from unittest.mock import patch

from app.core.security import get_password_hash, create_access_token, create_refresh_token
from app.models.user import User


class TestLoginRoute:
    """Tests for POST /api/auth/login."""

    @pytest.mark.asyncio
    async def test_login_success(self, client, admin_user):
        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "testpassword123",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client, admin_user):
        response = await client.post("/api/auth/login", json={
            "email": "admin@test.com",
            "password": "wrongpassword",
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client):
        response = await client.post("/api/auth/login", json={
            "email": "nobody@test.com",
            "password": "anypassword",
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_disabled_user(self, client, inactive_user):
        response = await client.post("/api/auth/login", json={
            "email": "inactive@test.com",
            "password": "testpassword123",
        })
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_login_invalid_email_format(self, client):
        response = await client.post("/api/auth/login", json={
            "email": "not-an-email",
            "password": "whatever",
        })
        assert response.status_code == 422


class TestRefreshRoute:
    """Tests for POST /api/auth/refresh."""

    @pytest.mark.asyncio
    async def test_refresh_success(self, client, admin_user):
        refresh_token = create_refresh_token(data={"sub": admin_user.id})
        response = await client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client):
        response = await client.post("/api/auth/refresh", json={
            "refresh_token": "invalid-token",
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_fails(self, client, admin_user):
        access_token = create_access_token(data={"sub": admin_user.id})
        response = await client.post("/api/auth/refresh", json={
            "refresh_token": access_token,
        })
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_disabled_user(self, client, inactive_user):
        refresh_token = create_refresh_token(data={"sub": inactive_user.id})
        response = await client.post("/api/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert response.status_code == 403


class TestMeRoute:
    """Tests for GET /api/auth/me."""

    @pytest.mark.asyncio
    async def test_me_authenticated(self, client, admin_user, auth_headers):
        response = await client.get("/api/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "admin@test.com"
        assert data["role"] == "admin"

    @pytest.mark.asyncio
    async def test_me_no_auth(self, client):
        response = await client.get("/api/auth/me")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_me_invalid_token(self, client):
        response = await client.get("/api/auth/me", headers={
            "Authorization": "Bearer invalid-token"
        })
        assert response.status_code == 401
