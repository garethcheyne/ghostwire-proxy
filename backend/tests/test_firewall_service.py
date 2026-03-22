"""Tests for firewall connector services."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from app.services.firewall_service import (
    RouterOSConnector,
    UniFiConnector,
    PfSenseConnector,
    OPNsenseConnector,
    get_connector,
)
from app.models.firewall import FirewallConnector


@pytest.fixture
def mock_routeros_connector():
    """Create a mock RouterOS connector model."""
    connector = MagicMock(spec=FirewallConnector)
    connector.id = "test-routeros-id"
    connector.name = "Test RouterOS"
    connector.connector_type = "routeros"
    connector.host = "192.168.1.1"
    connector.port = 8728
    connector.username = "admin"
    connector.password = "encrypted_password"
    connector.api_key = None
    connector.site_id = None
    connector.address_list_name = "ghostwire-blocked"
    connector.enabled = True
    return connector


@pytest.fixture
def mock_unifi_connector():
    """Create a mock UniFi connector model."""
    connector = MagicMock(spec=FirewallConnector)
    connector.id = "test-unifi-id"
    connector.name = "Test UniFi"
    connector.connector_type = "unifi"
    connector.host = "192.168.1.1"
    connector.port = 443
    connector.username = None
    connector.password = None
    connector.api_key = "encrypted_api_key"
    connector.site_id = "default"
    connector.address_list_name = "Ghostwire Blocked"
    connector.enabled = True
    return connector


@pytest.fixture
def mock_pfsense_connector():
    """Create a mock pfSense connector model."""
    connector = MagicMock(spec=FirewallConnector)
    connector.id = "test-pfsense-id"
    connector.name = "Test pfSense"
    connector.connector_type = "pfsense"
    connector.host = "192.168.1.1"
    connector.port = 443
    connector.username = None
    connector.password = None
    connector.api_key = "encrypted_api_key"
    connector.site_id = None
    connector.address_list_name = "ghostwire_blocked"
    connector.enabled = True
    return connector


@pytest.fixture
def mock_opnsense_connector():
    """Create a mock OPNsense connector model."""
    connector = MagicMock(spec=FirewallConnector)
    connector.id = "test-opnsense-id"
    connector.name = "Test OPNsense"
    connector.connector_type = "opnsense"
    connector.host = "192.168.1.1"
    connector.port = 443
    connector.username = None
    connector.password = "encrypted_secret"
    connector.api_key = "encrypted_api_key"
    connector.site_id = None
    connector.address_list_name = "ghostwire_blocked"
    connector.enabled = True
    return connector


class TestGetConnector:
    """Tests for the connector factory function."""

    def test_get_routeros_connector(self, mock_routeros_connector):
        """Test getting a RouterOS connector."""
        connector = get_connector(mock_routeros_connector)
        assert isinstance(connector, RouterOSConnector)

    def test_get_unifi_connector(self, mock_unifi_connector):
        """Test getting a UniFi connector."""
        connector = get_connector(mock_unifi_connector)
        assert isinstance(connector, UniFiConnector)

    def test_get_pfsense_connector(self, mock_pfsense_connector):
        """Test getting a pfSense connector."""
        connector = get_connector(mock_pfsense_connector)
        assert isinstance(connector, PfSenseConnector)

    def test_get_opnsense_connector(self, mock_opnsense_connector):
        """Test getting an OPNsense connector."""
        connector = get_connector(mock_opnsense_connector)
        assert isinstance(connector, OPNsenseConnector)

    def test_get_unknown_connector(self):
        """Test getting an unknown connector type raises error."""
        connector = MagicMock()
        connector.connector_type = "unknown"
        with pytest.raises(ValueError, match="Unknown connector type"):
            get_connector(connector)


class TestRouterOSConnector:
    """Tests for RouterOS connector."""

    @pytest.mark.asyncio
    async def test_test_connection_success(self, mock_routeros_connector):
        """Test successful connection test."""
        connector = RouterOSConnector(mock_routeros_connector)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"name": "MikroTik"}

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            with patch("app.services.firewall_service.decrypt_data", return_value="password"):
                result = await connector.test_connection()

        assert result["success"] is True
        assert "MikroTik" in result.get("identity", "")

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, mock_routeros_connector):
        """Test failed connection test."""
        connector = RouterOSConnector(mock_routeros_connector)

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            with patch("app.services.firewall_service.decrypt_data", return_value="password"):
                result = await connector.test_connection()

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_test_connection_exception(self, mock_routeros_connector):
        """Test connection test with exception."""
        connector = RouterOSConnector(mock_routeros_connector)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Connection refused")
            )
            with patch("app.services.firewall_service.decrypt_data", return_value="password"):
                result = await connector.test_connection()

        assert result["success"] is False
        assert "Connection refused" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_add_to_blocklist_success(self, mock_routeros_connector):
        """Test successful add to blocklist."""
        connector = RouterOSConnector(mock_routeros_connector)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.put = AsyncMock(
                return_value=mock_response
            )
            with patch("app.services.firewall_service.decrypt_data", return_value="password"):
                result = await connector.add_to_blocklist("192.0.2.1", "Test block")

        assert result is True


class TestUniFiConnector:
    """Tests for UniFi connector."""

    @pytest.mark.asyncio
    async def test_test_connection_success(self, mock_unifi_connector):
        """Test successful connection test."""
        connector = UniFiConnector(mock_unifi_connector)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"id": "site-1", "name": "Default"}],
            "totalCount": 1
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            with patch("app.services.firewall_service.decrypt_data", return_value="api_key"):
                result = await connector.test_connection()

        assert result["success"] is True
        assert "Connected to UniFi" in result.get("info", "")

    @pytest.mark.asyncio
    async def test_test_connection_invalid_api_key(self, mock_unifi_connector):
        """Test connection with invalid API key."""
        connector = UniFiConnector(mock_unifi_connector)

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            with patch("app.services.firewall_service.decrypt_data", return_value="bad_key"):
                result = await connector.test_connection()

        assert result["success"] is False
        assert "Invalid API key" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_add_to_blocklist_creates_group(self, mock_unifi_connector):
        """Test add to blocklist creates group if not exists."""
        connector = UniFiConnector(mock_unifi_connector)

        # First call - list groups (empty)
        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.return_value = {"data": []}

        # Second call - create group
        create_response = MagicMock()
        create_response.status_code = 200
        create_response.json.return_value = {
            "meta": {"rc": "ok"},
            "data": [{"_id": "new-group-id", "group_members": []}]
        }

        # Third call - get group
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            "data": [{"_id": "new-group-id", "group_members": []}]
        }

        # Fourth call - update group
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = {"meta": {"rc": "ok"}}

        with patch("httpx.AsyncClient") as mock_client:
            client_mock = mock_client.return_value.__aenter__.return_value
            client_mock.get = AsyncMock(side_effect=[list_response, get_response])
            client_mock.post = AsyncMock(return_value=create_response)
            client_mock.put = AsyncMock(return_value=update_response)

            with patch("app.services.firewall_service.decrypt_data", return_value="api_key"):
                result = await connector.add_to_blocklist("192.0.2.1", "Test")

        assert result is True

    @pytest.mark.asyncio
    async def test_remove_from_blocklist_success(self, mock_unifi_connector):
        """Test successful remove from blocklist."""
        connector = UniFiConnector(mock_unifi_connector)

        # List groups
        list_response = MagicMock()
        list_response.status_code = 200
        list_response.json.return_value = {
            "data": [{"_id": "group-id", "name": "Ghostwire Blocked", "group_type": "address-group", "group_members": ["192.0.2.1"]}]
        }

        # Get group
        get_response = MagicMock()
        get_response.status_code = 200
        get_response.json.return_value = {
            "data": [{"_id": "group-id", "group_members": ["192.0.2.1"]}]
        }

        # Update group
        update_response = MagicMock()
        update_response.status_code = 200
        update_response.json.return_value = {"meta": {"rc": "ok"}}

        with patch("httpx.AsyncClient") as mock_client:
            client_mock = mock_client.return_value.__aenter__.return_value
            client_mock.get = AsyncMock(side_effect=[list_response, get_response])
            client_mock.put = AsyncMock(return_value=update_response)

            with patch("app.services.firewall_service.decrypt_data", return_value="api_key"):
                result = await connector.remove_from_blocklist("192.0.2.1")

        assert result is True


class TestPfSenseConnector:
    """Tests for pfSense connector."""

    @pytest.mark.asyncio
    async def test_test_connection_success(self, mock_pfsense_connector):
        """Test successful connection test."""
        connector = PfSenseConnector(mock_pfsense_connector)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            with patch("app.services.firewall_service.decrypt_data", return_value="api_key"):
                result = await connector.test_connection()

        assert result["success"] is True


class TestOPNsenseConnector:
    """Tests for OPNsense connector."""

    @pytest.mark.asyncio
    async def test_test_connection_success(self, mock_opnsense_connector):
        """Test successful connection test."""
        connector = OPNsenseConnector(mock_opnsense_connector)

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            with patch("app.services.firewall_service.decrypt_data", return_value="api_key"):
                result = await connector.test_connection()

        assert result["success"] is True
