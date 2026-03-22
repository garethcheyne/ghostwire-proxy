"""Tests for preset service — list, get, and apply security presets."""

import pytest
import json
import uuid
from unittest.mock import patch, MagicMock
from pathlib import Path

from app.services.preset_service import list_presets, get_preset, apply_preset


class TestListPresets:
    """Tests for listing security presets."""

    def test_list_all_presets(self):
        presets = list_presets()
        assert isinstance(presets, list)
        assert len(presets) > 0

    def test_preset_has_required_fields(self):
        presets = list_presets()
        for preset in presets:
            assert "id" in preset
            assert "name" in preset
            assert "description" in preset
            assert "category" in preset
            assert "rule_count" in preset

    def test_filter_by_waf_category(self):
        presets = list_presets(category="waf")
        assert all(p["category"] == "waf" for p in presets)

    def test_filter_by_geoip_category(self):
        presets = list_presets(category="geoip")
        assert all(p["category"] == "geoip" for p in presets)

    def test_filter_by_rate_limit_category(self):
        presets = list_presets(category="rate_limit")
        assert all(p["category"] == "rate_limit" for p in presets)

    def test_filter_by_threat_response_category(self):
        presets = list_presets(category="threat_response")
        assert all(p["category"] == "threat_response" for p in presets)

    def test_filter_nonexistent_category(self):
        presets = list_presets(category="nonexistent")
        assert presets == []

    def test_presets_have_valid_severity(self):
        presets = list_presets()
        for preset in presets:
            assert preset["severity"] in ("low", "medium", "high", "critical")

    def test_presets_have_positive_rule_count(self):
        presets = list_presets()
        for preset in presets:
            assert preset["rule_count"] > 0

    def test_list_presets_no_dir(self, tmp_path):
        """Test with non-existent presets directory."""
        with patch("app.services.preset_service.PRESETS_DIR", tmp_path / "nope"):
            result = list_presets()
        assert result == []


class TestGetPreset:
    """Tests for getting preset details."""

    def test_get_existing_preset(self):
        presets = list_presets()
        if presets:
            preset = get_preset(presets[0]["id"])
            assert preset is not None
            assert preset["id"] == presets[0]["id"]

    def test_get_nonexistent_preset(self):
        result = get_preset("does-not-exist")
        assert result is None

    def test_get_preset_has_rules(self):
        presets = list_presets(category="waf")
        if presets:
            preset = get_preset(presets[0]["id"])
            assert "rules" in preset or "thresholds" in preset

    def test_get_preset_no_dir(self, tmp_path):
        with patch("app.services.preset_service.PRESETS_DIR", tmp_path / "nope"):
            result = get_preset("any-id")
        assert result is None

    def test_get_rate_limit_preset(self):
        preset = get_preset("ratelimit-api")
        if preset:
            assert preset["category"] == "rate_limit"
            assert "rules" in preset

    def test_get_waf_preset(self):
        presets = list_presets(category="waf")
        if presets:
            preset = get_preset(presets[0]["id"])
            assert "rules" in preset
            for rule in preset["rules"]:
                assert "name" in rule
                assert "pattern" in rule


class TestApplyPreset:
    """Tests for applying presets to the database."""

    @pytest.mark.asyncio
    async def test_apply_waf_preset(self, db_session):
        presets = list_presets(category="waf")
        if not presets:
            pytest.skip("No WAF presets available")
        result = await apply_preset(presets[0]["id"], db_session, "test-user-id")
        assert result["category"] == "waf"
        assert result["items_created"] > 0
        assert all(item["type"] == "waf_rule" for item in result["items"])

    @pytest.mark.asyncio
    async def test_apply_geoip_preset(self, db_session):
        presets = list_presets(category="geoip")
        if not presets:
            pytest.skip("No GeoIP presets available")
        result = await apply_preset(presets[0]["id"], db_session, "test-user-id")
        assert result["category"] == "geoip"
        assert result["items_created"] > 0

    @pytest.mark.asyncio
    async def test_apply_rate_limit_preset(self, db_session):
        presets = list_presets(category="rate_limit")
        if not presets:
            pytest.skip("No rate limit presets available")
        result = await apply_preset(presets[0]["id"], db_session, "test-user-id")
        assert result["category"] == "rate_limit"
        assert result["items_created"] > 0

    @pytest.mark.asyncio
    async def test_apply_threat_response_preset(self, db_session):
        presets = list_presets(category="threat_response")
        if not presets:
            pytest.skip("No threat_response presets available")
        result = await apply_preset(presets[0]["id"], db_session, "test-user-id")
        assert result["category"] == "threat_response"
        assert result["items_created"] > 0

    @pytest.mark.asyncio
    async def test_apply_nonexistent_preset(self, db_session):
        with pytest.raises(ValueError, match="Preset not found"):
            await apply_preset("nonexistent", db_session, "test-user-id")

    @pytest.mark.asyncio
    async def test_apply_preset_creates_audit_log(self, db_session):
        from app.models.audit_log import AuditLog
        from sqlalchemy import select

        presets = list_presets(category="waf")
        if not presets:
            pytest.skip("No WAF presets available")
        await apply_preset(presets[0]["id"], db_session, "test-user-id", client_ip="127.0.0.1")

        result = await db_session.execute(select(AuditLog).where(AuditLog.action == "preset_applied"))
        log = result.scalar_one_or_none()
        assert log is not None
        assert log.user_id == "test-user-id"
        assert log.ip_address == "127.0.0.1"

    @pytest.mark.asyncio
    async def test_apply_preset_with_proxy_host_id(self, db_session):
        presets = list_presets(category="rate_limit")
        if not presets:
            pytest.skip("No rate limit presets available")
        result = await apply_preset(
            presets[0]["id"], db_session, "test-user-id",
            proxy_host_id="host-123",
        )
        assert result["items_created"] > 0

    @pytest.mark.asyncio
    async def test_apply_preset_return_structure(self, db_session):
        presets = list_presets()
        if not presets:
            pytest.skip("No presets available")
        result = await apply_preset(presets[0]["id"], db_session, "test-user-id")
        assert "preset_id" in result
        assert "preset_name" in result
        assert "category" in result
        assert "items_created" in result
        assert "items" in result
        assert isinstance(result["items"], list)
