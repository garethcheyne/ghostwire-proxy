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
    connector.address_list_name = "Ghostwire Block"
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
    async def test_test_connection_success_with_findings(self, mock_unifi_connector):
        """Test successful connection test returns findings about lists and policies."""
        connector = UniFiConnector(mock_unifi_connector)

        # Sites response (called twice: once directly, once by _get_site_uuid)
        def make_sites_response():
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {
                "data": [{"id": "site-1", "internalReference": "default", "name": "Default"}],
                "totalCount": 1,
            }
            return r

        # Traffic matching lists response (both IPv4 and IPv6 exist)
        lists_response = MagicMock()
        lists_response.status_code = 200
        lists_response.json.return_value = {
            "data": [
                {"id": "list-v4", "name": "Ghostwire Block IPv4", "type": "IPV4_ADDRESSES"},
                {"id": "list-v6", "name": "Ghostwire Block IPv6", "type": "IPV6_ADDRESSES"},
            ]
        }

        # Policies response (both exist)
        policies_response = MagicMock()
        policies_response.status_code = 200
        policies_response.json.return_value = {
            "data": [
                {"id": "pol-v4", "name": "Ghostwire Drop IPv4"},
                {"id": "pol-v6", "name": "Ghostwire Drop IPv6"},
            ]
        }

        # Zones response
        zones_response = MagicMock()
        zones_response.status_code = 200
        zones_response.json.return_value = {
            "data": [
                {"id": "zone-ext", "name": "External"},
                {"id": "zone-int", "name": "Internal"},
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            client_mock = mock_client.return_value.__aenter__.return_value
            client_mock.get = AsyncMock(side_effect=[
                make_sites_response(),  # direct sites call
                make_sites_response(),  # _get_site_uuid call
                lists_response, policies_response, zones_response
            ])
            with patch("app.services.firewall_service.decrypt_data", return_value="api_key"):
                result = await connector.test_connection()

        assert result["success"] is True
        assert "Connected to UniFi" in result.get("info", "")
        assert "findings" in result
        findings = result["findings"]
        assert len(findings) >= 6  # API, site, 2 lists, 2 policies, zone
        statuses = [f["status"] for f in findings]
        assert all(s == "ok" for s in statuses)

    @pytest.mark.asyncio
    async def test_test_connection_missing_ipv6_list(self, mock_unifi_connector):
        """Test connection reports missing IPv6 list."""
        connector = UniFiConnector(mock_unifi_connector)

        def make_sites_response():
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {
                "data": [{"id": "site-1", "internalReference": "default", "name": "Default"}],
                "totalCount": 1,
            }
            return r

        # Only IPv4 list exists
        lists_response = MagicMock()
        lists_response.status_code = 200
        lists_response.json.return_value = {
            "data": [{"id": "list-v4", "name": "Ghostwire Block IPv4", "type": "IPV4_ADDRESSES"}]
        }

        policies_response = MagicMock()
        policies_response.status_code = 200
        policies_response.json.return_value = {
            "data": [{"id": "pol-v4", "name": "Ghostwire Drop IPv4"}]
        }

        zones_response = MagicMock()
        zones_response.status_code = 200
        zones_response.json.return_value = {"data": [{"id": "zone-ext", "name": "External"}]}

        with patch("httpx.AsyncClient") as mock_client:
            client_mock = mock_client.return_value.__aenter__.return_value
            client_mock.get = AsyncMock(side_effect=[
                make_sites_response(), make_sites_response(),
                lists_response, policies_response, zones_response
            ])
            with patch("app.services.firewall_service.decrypt_data", return_value="api_key"):
                result = await connector.test_connection()

        assert result["success"] is True
        findings = result["findings"]
        ipv6_list_finding = [f for f in findings if f["item"] == "IPv6 Address List"][0]
        assert ipv6_list_finding["status"] == "missing"
        ipv6_policy_finding = [f for f in findings if f["item"] == "IPv6 Drop Policy"][0]
        assert ipv6_policy_finding["status"] == "missing"

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
    async def test_add_ipv4_to_blocklist(self, mock_unifi_connector):
        """Test adding an IPv4 address goes to the IPv4 list."""
        connector = UniFiConnector(mock_unifi_connector)

        # _get_site_uuid GET
        sites_response = MagicMock()
        sites_response.status_code = 200
        sites_response.json.return_value = {
            "data": [{"id": "site-uuid", "internalReference": "default", "name": "Default"}]
        }

        # _get_or_create_traffic_matching_list GET — IPv4 list exists
        lists_response = MagicMock()
        lists_response.status_code = 200
        lists_response.json.return_value = {
            "data": [{"id": "list-v4", "name": "Ghostwire Block IPv4", "type": "IPV4_ADDRESSES"}]
        }

        # _get_or_create_firewall_policy GET — Policy exists
        policies_response = MagicMock()
        policies_response.status_code = 200
        policies_response.json.return_value = {
            "data": [{"id": "pol-v4", "name": "Ghostwire Drop IPv4"}]
        }

        # _get_traffic_matching_list GET — current items
        list_detail_response = MagicMock()
        list_detail_response.status_code = 200
        list_detail_response.json.return_value = {
            "items": [{"type": "IP_ADDRESS", "value": "192.0.2.1"}]
        }

        update_response = MagicMock()
        update_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            client_mock = mock_client.return_value.__aenter__.return_value
            client_mock.get = AsyncMock(side_effect=[
                sites_response, lists_response, policies_response, list_detail_response
            ])
            client_mock.post = AsyncMock()
            client_mock.put = AsyncMock(return_value=update_response)

            with patch("app.services.firewall_service.decrypt_data", return_value="api_key"):
                result = await connector.add_to_blocklist("10.0.0.1", "Test")

        assert result is True
        # Verify the PUT was called with IPv4 list name
        put_call = client_mock.put.call_args
        assert put_call[1]["json"]["name"] == "Ghostwire Block IPv4"
        assert put_call[1]["json"]["type"] == "IPV4_ADDRESSES"

    @pytest.mark.asyncio
    async def test_add_ipv6_to_blocklist(self, mock_unifi_connector):
        """Test adding an IPv6 address goes to the IPv6 list."""
        connector = UniFiConnector(mock_unifi_connector)

        sites_response = MagicMock()
        sites_response.status_code = 200
        sites_response.json.return_value = {
            "data": [{"id": "site-uuid", "internalReference": "default", "name": "Default"}]
        }

        # No existing lists — triggers create
        empty_lists_response = MagicMock()
        empty_lists_response.status_code = 200
        empty_lists_response.json.return_value = {"data": []}

        # No existing policies — triggers create
        empty_policies_response = MagicMock()
        empty_policies_response.status_code = 200
        empty_policies_response.json.return_value = {"data": []}

        # Zones
        zones_response = MagicMock()
        zones_response.status_code = 200
        zones_response.json.return_value = {
            "data": [{"id": "zone-ext", "name": "External"}, {"id": "zone-int", "name": "Internal"}]
        }

        # Get list detail after create (empty so the new IP gets added)
        list_detail_response = MagicMock()
        list_detail_response.status_code = 200
        list_detail_response.json.return_value = {
            "items": []
        }

        # POST responses for create list and create policy
        create_list_response = MagicMock()
        create_list_response.status_code = 200
        create_list_response.json.return_value = {"id": "new-v6-list"}

        create_policy_response = MagicMock()
        create_policy_response.status_code = 200
        create_policy_response.json.return_value = {"id": "new-v6-policy"}

        update_response = MagicMock()
        update_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            client_mock = mock_client.return_value.__aenter__.return_value
            client_mock.get = AsyncMock(side_effect=[
                sites_response, empty_lists_response,
                empty_policies_response, zones_response,
                list_detail_response,
            ])
            client_mock.post = AsyncMock(side_effect=[
                create_list_response, create_policy_response,
            ])
            client_mock.put = AsyncMock(return_value=update_response)

            with patch("app.services.firewall_service.decrypt_data", return_value="api_key"):
                result = await connector.add_to_blocklist("2001:db8::1", "Test IPv6")

        assert result is True
        # Verify the PUT was called with IPv6 list name
        put_call = client_mock.put.call_args
        assert put_call[1]["json"]["name"] == "Ghostwire Block IPv6"
        assert put_call[1]["json"]["type"] == "IPV6_ADDRESSES"

    @pytest.mark.asyncio
    async def test_remove_from_blocklist_success(self, mock_unifi_connector):
        """Test successful remove from blocklist."""
        connector = UniFiConnector(mock_unifi_connector)

        # GET #1 - sites
        sites_response = MagicMock()
        sites_response.status_code = 200
        sites_response.json.return_value = {
            "data": [{"id": "site-uuid", "internalReference": "default", "name": "Default"}]
        }

        # GET #2 - traffic-matching-lists (finds existing list)
        lists_response = MagicMock()
        lists_response.status_code = 200
        lists_response.json.return_value = {
            "data": [{"id": "list-id", "name": "Ghostwire Block IPv4", "type": "IPV4_ADDRESSES"}]
        }

        # GET #3 - traffic-matching-lists/{id} (get current items)
        list_detail_response = MagicMock()
        list_detail_response.status_code = 200
        list_detail_response.json.return_value = {
            "items": [{"type": "IP_ADDRESS", "value": "192.0.2.1"}, {"type": "IP_ADDRESS", "value": "10.0.0.5"}]
        }

        # PUT - update traffic matching list without the removed IP
        update_response = MagicMock()
        update_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            client_mock = mock_client.return_value.__aenter__.return_value
            client_mock.get = AsyncMock(side_effect=[
                sites_response, lists_response, list_detail_response
            ])
            client_mock.post = AsyncMock()  # shouldn't be called
            client_mock.put = AsyncMock(return_value=update_response)

            with patch("app.services.firewall_service.decrypt_data", return_value="api_key"):
                result = await connector.remove_from_blocklist("10.0.0.5")

        assert result is True

    def test_is_ipv6(self, mock_unifi_connector):
        """Test IPv4/IPv6 detection."""
        connector = UniFiConnector(mock_unifi_connector)
        assert connector._is_ipv6("192.168.1.1") is False
        assert connector._is_ipv6("10.0.0.1") is False
        assert connector._is_ipv6("2001:db8::1") is True
        assert connector._is_ipv6("::1") is True
        assert connector._is_ipv6("fe80::1") is True
        assert connector._is_ipv6("not-an-ip") is False

    def test_list_name_derivation(self, mock_unifi_connector):
        """Test that list names are derived correctly from base name."""
        connector = UniFiConnector(mock_unifi_connector)
        # mock_unifi_connector has address_list_name = "Ghostwire Block"
        assert connector._get_list_name_ipv4() == "Ghostwire Block IPv4"
        assert connector._get_list_name_ipv6() == "Ghostwire Block IPv6"

    def test_list_name_strips_existing_suffix(self, mock_unifi_connector):
        """Test that existing IPv4/IPv6 suffix is stripped before re-deriving."""
        mock_unifi_connector.address_list_name = "Ghostwire Block IPv4"
        connector = UniFiConnector(mock_unifi_connector)
        assert connector._get_list_base_name() == "Ghostwire Block"
        assert connector._get_list_name_ipv4() == "Ghostwire Block IPv4"
        assert connector._get_list_name_ipv6() == "Ghostwire Block IPv6"

    def test_policy_names(self, mock_unifi_connector):
        """Test firewall policy names."""
        connector = UniFiConnector(mock_unifi_connector)
        assert connector._get_policy_name_ipv4() == "Ghostwire Drop IPv4"
        assert connector._get_policy_name_ipv6() == "Ghostwire Drop IPv6"


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
