"""Tests for presets API routes."""

import pytest

from app.models.user import User


class TestListPresets:
    """Tests for GET /api/presets."""

    @pytest.mark.asyncio
    async def test_list_presets(self, client, admin_user, auth_headers):
        response = await client.get("/api/presets", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_list_presets_filter_category(self, client, admin_user, auth_headers):
        response = await client.get("/api/presets?category=waf", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        for preset in data:
            assert preset["category"] == "waf"

    @pytest.mark.asyncio
    async def test_list_presets_no_auth(self, client):
        response = await client.get("/api/presets")
        assert response.status_code == 403


class TestGetPresetDetail:
    """Tests for GET /api/presets/{preset_id}."""

    @pytest.mark.asyncio
    async def test_get_preset(self, client, admin_user, auth_headers):
        # Get list first to get an ID
        list_resp = await client.get("/api/presets", headers=auth_headers)
        presets = list_resp.json()
        if presets:
            preset_id = presets[0]["id"]
            response = await client.get(f"/api/presets/{preset_id}", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == preset_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_preset(self, client, admin_user, auth_headers):
        response = await client.get("/api/presets/nonexistent", headers=auth_headers)
        assert response.status_code == 404


class TestApplyPreset:
    """Tests for POST /api/presets/{preset_id}/apply."""

    @pytest.mark.asyncio
    async def test_apply_preset(self, client, admin_user, auth_headers):
        list_resp = await client.get("/api/presets", headers=auth_headers)
        presets = list_resp.json()
        if presets:
            preset_id = presets[0]["id"]
            response = await client.post(
                f"/api/presets/{preset_id}/apply",
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["preset_id"] == preset_id
            assert data["items_created"] > 0

    @pytest.mark.asyncio
    async def test_apply_nonexistent_preset(self, client, admin_user, auth_headers):
        response = await client.post(
            "/api/presets/nonexistent/apply",
            headers=auth_headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_apply_preset_no_auth(self, client):
        response = await client.post("/api/presets/any/apply")
        assert response.status_code == 403
