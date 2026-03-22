"""Tests for users API routes."""

import pytest

from app.models.user import User


class TestListUsers:
    """Tests for GET /api/users."""

    @pytest.mark.asyncio
    async def test_list_users(self, client, admin_user, auth_headers):
        response = await client.get("/api/users/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_list_users_no_auth(self, client):
        response = await client.get("/api/users/")
        assert response.status_code == 403


class TestCreateUser:
    """Tests for POST /api/users."""

    @pytest.mark.asyncio
    async def test_create_user(self, client, admin_user, auth_headers):
        response = await client.post("/api/users/", headers=auth_headers, json={
            "email": "newuser@test.com",
            "name": "New User",
            "password": "securepassword123",
            "role": "user",
        })
        assert response.status_code in (200, 201)
        data = response.json()
        assert data["email"] == "newuser@test.com"

    @pytest.mark.asyncio
    async def test_create_duplicate_email(self, client, admin_user, auth_headers):
        # First create
        await client.post("/api/users/", headers=auth_headers, json={
            "email": "dup@test.com",
            "name": "Dup User",
            "password": "password123",
            "role": "user",
        })
        # Duplicate
        response = await client.post("/api/users/", headers=auth_headers, json={
            "email": "dup@test.com",
            "name": "Dup User 2",
            "password": "password123",
            "role": "user",
        })
        assert response.status_code in (400, 409, 422)


class TestGetUser:
    """Tests for GET /api/users/{id}."""

    @pytest.mark.asyncio
    async def test_get_user(self, client, admin_user, auth_headers):
        response = await client.get(f"/api/users/{admin_user.id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["id"] == admin_user.id

    @pytest.mark.asyncio
    async def test_get_nonexistent_user(self, client, admin_user, auth_headers):
        response = await client.get("/api/users/nonexistent-id", headers=auth_headers)
        assert response.status_code == 404


class TestUpdateUser:
    """Tests for PUT /api/users/{id}."""

    @pytest.mark.asyncio
    async def test_update_user_name(self, client, admin_user, auth_headers):
        response = await client.put(
            f"/api/users/{admin_user.id}",
            headers=auth_headers,
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"


class TestDeleteUser:
    """Tests for DELETE /api/users/{id}."""

    @pytest.mark.asyncio
    async def test_delete_user(self, client, admin_user, regular_user, auth_headers):
        response = await client.delete(
            f"/api/users/{regular_user.id}",
            headers=auth_headers,
        )
        assert response.status_code in (200, 204)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user(self, client, admin_user, auth_headers):
        response = await client.delete("/api/users/nonexistent-id", headers=auth_headers)
        assert response.status_code == 404
