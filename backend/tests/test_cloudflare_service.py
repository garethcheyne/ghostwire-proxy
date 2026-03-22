"""Tests for cloudflare service."""

import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.cloudflare_service import CloudflareClient


class TestCloudflareClient:
    """Tests for the Cloudflare API client."""

    def _make_client(self, token="test-token"):
        return CloudflareClient(api_token=token)

    @pytest.mark.asyncio
    async def test_verify_token_success(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True, "result": {"status": "active"}}

        with patch("httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
            success, msg = await client.verify_token()

        assert success is True

    @pytest.mark.asyncio
    async def test_verify_token_failure(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"success": False, "errors": [{"message": "Invalid token"}]}

        with patch("httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
            success, msg = await client.verify_token()

        assert success is False

    @pytest.mark.asyncio
    async def test_list_zones_success(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "result": [{"id": "zone-1", "name": "example.com"}],
        }

        with patch("httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                get=AsyncMock(return_value=mock_resp)
            ))
            mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
            success, zones = await client.list_zones()

        assert success is True
        assert len(zones) == 1
        assert zones[0]["name"] == "example.com"

    @pytest.mark.asyncio
    async def test_create_dns_record_success(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "success": True,
            "result": {"id": "record-1", "type": "A", "name": "test.example.com"},
        }

        with patch("httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                post=AsyncMock(return_value=mock_resp)
            ))
            mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
            success, record = await client.create_dns_record(
                "zone-1", "A", "test.example.com", "1.2.3.4"
            )

        assert success is True
        assert record["type"] == "A"

    @pytest.mark.asyncio
    async def test_delete_dns_record_success(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True, "result": {"id": "record-1"}}

        with patch("httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                delete=AsyncMock(return_value=mock_resp)
            ))
            mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
            success, msg = await client.delete_dns_record("zone-1", "record-1")

        assert success is True
