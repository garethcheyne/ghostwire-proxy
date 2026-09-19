"""Tests for settings API routes."""

import pytest

from app.models.setting import Setting


class TestGetSettings:
    """Tests for GET /api/settings."""

    @pytest.mark.asyncio
    async def test_get_all_settings(self, client, admin_user, auth_headers):
        response = await client.get("/api/settings/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_get_settings_no_auth(self, client):
        response = await client.get("/api/settings/")
        assert response.status_code == 401


class TestGetSetting:
    """Tests for GET /api/settings/{key}."""

    @pytest.mark.asyncio
    async def test_get_specific_setting(self, client, admin_user, auth_headers, db_session):
        # Create a setting
        setting = Setting(key="test_key", value="test_value")
        db_session.add(setting)
        await db_session.commit()

        response = await client.get("/api/settings/test_key", headers=auth_headers)
        assert response.status_code == 200


class TestUpdateSetting:
    """Tests for PUT /api/settings/{key}."""

    @pytest.mark.asyncio
    async def test_update_setting(self, client, admin_user, auth_headers):
        response = await client.put(
            "/api/settings/test_key",
            headers=auth_headers,
            json={"value": "new_value"},
        )
        assert response.status_code == 200


class TestDefaultSiteSettings:
    """Tests for GET/PUT /api/settings/default-site.

    Note: The GET /default-site path may be captured by the /{key} route
    depending on route ordering. We test via the specific key lookup.
    """

    @pytest.mark.asyncio
    async def test_get_default_site_via_key(self, client, admin_user, auth_headers, db_session):
        # Set the behavior setting so it exists
        from app.models.setting import Setting
        db_session.add(Setting(key="default_site_behavior", value="congratulations"))
        await db_session.commit()

        response = await client.get("/api/settings/default_site_behavior", headers=auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_update_default_site(self, client, admin_user, auth_headers, tmp_path):
        """Writes _default.conf and reloads nginx (nginx itself is mocked: CI has none)."""
        from unittest.mock import patch
        from app.core.config import settings as app_settings

        with patch.object(app_settings, "nginx_config_path", str(tmp_path)),              patch("app.services.openresty_service.backup_configs"),              patch("app.services.openresty_service.restore_configs") as restore,              patch("app.services.openresty_service.test_nginx_config", return_value=(True, "ok")),              patch("app.services.openresty_service.reload_nginx", return_value=(True, "ok")):
            response = await client.put(
                "/api/settings/default-site",
                headers=auth_headers,
                json={"behavior": "404"},
            )

        assert response.status_code == 200
        config = (tmp_path / "_default.conf").read_text()
        assert "return 404;" in config
        assert "location /.well-known/acme-challenge/" in config
        restore.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_default_site_rolls_back_bad_config(self, client, admin_user, auth_headers, tmp_path):
        from unittest.mock import patch
        from app.core.config import settings as app_settings

        with patch.object(app_settings, "nginx_config_path", str(tmp_path)),              patch("app.services.openresty_service.backup_configs"),              patch("app.services.openresty_service.restore_configs") as restore,              patch("app.services.openresty_service.test_nginx_config", return_value=(False, "syntax error")),              patch("app.services.openresty_service.reload_nginx") as reload:
            response = await client.put(
                "/api/settings/default-site",
                headers=auth_headers,
                json={"behavior": "404"},
            )

        assert response.status_code == 400
        restore.assert_called_once()
        reload.assert_not_called()


class TestReloadNginx:
    """Tests for POST /api/settings/reload-nginx."""

    @pytest.mark.asyncio
    async def test_reload_nginx_no_auth(self, client):
        response = await client.post("/api/settings/reload-nginx")
        assert response.status_code == 401
