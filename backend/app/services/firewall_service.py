"""Firewall connector services for RouterOS, UniFi, pfSense, OPNsense."""

import logging
from typing import Optional
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.firewall import FirewallConnector, FirewallBlocklist
from app.core.security import decrypt_data

logger = logging.getLogger(__name__)


class BaseFirewallConnector:
    """Base class for firewall connectors."""

    def __init__(self, connector: FirewallConnector):
        self.connector = connector
        self.host = connector.host
        self.port = connector.port
        self.username = connector.username

    async def test_connection(self) -> dict:
        raise NotImplementedError

    async def add_to_blocklist(self, ip: str, comment: str = "") -> bool:
        raise NotImplementedError

    async def remove_from_blocklist(self, ip: str) -> bool:
        raise NotImplementedError

    async def get_blocklist(self) -> list[str]:
        raise NotImplementedError


class RouterOSConnector(BaseFirewallConnector):
    """MikroTik RouterOS REST API connector."""

    def _get_base_url(self) -> str:
        port = self.port or 443
        return f"https://{self.host}:{port}/rest"

    def _get_auth(self) -> tuple[str, str]:
        password = decrypt_data(self.connector.password) if self.connector.password else ""
        return (self.username or "admin", password)

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                resp = await client.get(
                    f"{self._get_base_url()}/system/identity",
                    auth=self._get_auth(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return {"success": True, "identity": data.get("name", "unknown")}
                return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def add_to_blocklist(self, ip: str, comment: str = "") -> bool:
        list_name = self.connector.address_list_name or "ghostwire-blocked"
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                resp = await client.put(
                    f"{self._get_base_url()}/ip/firewall/address-list",
                    auth=self._get_auth(),
                    json={
                        "list": list_name,
                        "address": ip,
                        "comment": comment or f"Blocked by Ghostwire Proxy",
                    },
                )
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.error(f"RouterOS add_to_blocklist failed: {e}")
            return False

    async def remove_from_blocklist(self, ip: str) -> bool:
        list_name = self.connector.address_list_name or "ghostwire-blocked"
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                # Find the entry
                resp = await client.get(
                    f"{self._get_base_url()}/ip/firewall/address-list",
                    auth=self._get_auth(),
                    params={"list": list_name, "address": ip},
                )
                if resp.status_code == 200:
                    entries = resp.json()
                    for entry in entries:
                        entry_id = entry.get(".id")
                        if entry_id:
                            await client.delete(
                                f"{self._get_base_url()}/ip/firewall/address-list/{entry_id}",
                                auth=self._get_auth(),
                            )
                    return True
                return False
        except Exception as e:
            logger.error(f"RouterOS remove_from_blocklist failed: {e}")
            return False

    async def get_blocklist(self) -> list[str]:
        list_name = self.connector.address_list_name or "ghostwire-blocked"
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                resp = await client.get(
                    f"{self._get_base_url()}/ip/firewall/address-list",
                    auth=self._get_auth(),
                    params={"list": list_name},
                )
                if resp.status_code == 200:
                    return [e.get("address", "") for e in resp.json()]
                return []
        except Exception as e:
            logger.error(f"RouterOS get_blocklist failed: {e}")
            return []


class UniFiConnector(BaseFirewallConnector):
    """Ubiquiti UniFi Network Application API connector (v1 Integration API with zones)."""

    def _get_base_url(self) -> str:
        port = self.port or 443
        return f"https://{self.host}:{port}"

    def _get_headers(self) -> dict:
        """Get headers with API key authentication."""
        api_key = decrypt_data(self.connector.api_key) if self.connector.api_key else ""
        return {
            "X-API-KEY": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get_list_name(self) -> str:
        """Get the traffic matching list name for blocked IPs."""
        return self.connector.address_list_name or "Ghostwire - Blocked"

    def _get_policy_name(self) -> str:
        """Get the firewall policy name."""
        return "Ghostwire - Autoblock"

    async def _get_site_uuid(self, client: httpx.AsyncClient) -> str | None:
        """Get the site UUID from site name/id. New API requires UUID."""
        site_ref = self.connector.site_id or "default"

        resp = await client.get(
            f"{self._get_base_url()}/proxy/network/integration/v1/sites",
            headers=self._get_headers(),
        )
        if resp.status_code != 200:
            logger.error(f"UniFi: failed to list sites: HTTP {resp.status_code}")
            return None

        data = resp.json()
        sites = data.get("data", [])

        for site in sites:
            # Match by internalReference (old name like "default") or by name or by id
            if site.get("internalReference") == site_ref or site.get("name") == site_ref or site.get("id") == site_ref:
                return site.get("id")

        # If only one site, use it
        if len(sites) == 1:
            return sites[0].get("id")

        logger.error(f"UniFi: could not find site '{site_ref}'")
        return None

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                resp = await client.get(
                    f"{self._get_base_url()}/proxy/network/integration/v1/sites",
                    headers=self._get_headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    sites = data.get("data", [])
                    site_count = data.get("totalCount", len(sites))
                    site_names = [s.get("name", "Unknown") for s in sites[:3]]
                    return {"success": True, "info": f"Connected to UniFi v1 API ({site_count} site(s): {', '.join(site_names)})"}
                elif resp.status_code == 401:
                    return {"success": False, "error": "Invalid API key"}
                elif resp.status_code == 403:
                    return {"success": False, "error": "API key lacks permission"}
                return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _get_or_create_traffic_matching_list(self, client: httpx.AsyncClient, site_uuid: str) -> str | None:
        """Get or create the Traffic Matching List for blocked IPs."""
        list_name = self._get_list_name()

        # List existing traffic matching lists
        resp = await client.get(
            f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/traffic-matching-lists",
            headers=self._get_headers(),
        )
        if resp.status_code != 200:
            logger.error(f"UniFi: failed to list traffic matching lists: HTTP {resp.status_code} - {resp.text}")
            return None

        data = resp.json()
        lists = data.get("data", [])

        # Find existing list
        for lst in lists:
            if lst.get("name") == list_name and lst.get("type") == "IPV4_ADDRESSES":
                logger.info(f"UniFi: found existing traffic matching list '{list_name}'")
                return lst.get("id")

        # Create new list with a placeholder IP (required - can't be empty)
        resp = await client.post(
            f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/traffic-matching-lists",
            headers=self._get_headers(),
            json={
                "type": "IPV4_ADDRESSES",
                "name": list_name,
                "items": [{"type": "IP_ADDRESS", "value": "192.0.2.1"}],  # TEST-NET-1 placeholder
            },
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            list_id = data.get("id")
            if list_id:
                logger.info(f"UniFi: created traffic matching list '{list_name}' (ID: {list_id})")
                return list_id

        logger.error(f"UniFi: failed to create traffic matching list: {resp.status_code} - {resp.text}")
        return None

    async def _get_traffic_matching_list(self, client: httpx.AsyncClient, site_uuid: str, list_id: str) -> dict | None:
        """Get traffic matching list details by ID."""
        resp = await client.get(
            f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/traffic-matching-lists/{list_id}",
            headers=self._get_headers(),
        )
        if resp.status_code == 200:
            return resp.json()
        return None

    async def _get_firewall_zones(self, client: httpx.AsyncClient, site_uuid: str) -> dict:
        """Get firewall zones - returns dict with 'external' and 'internal' zone IDs."""
        resp = await client.get(
            f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/firewall/zones",
            headers=self._get_headers(),
        )
        if resp.status_code != 200:
            logger.error(f"UniFi: failed to list firewall zones: HTTP {resp.status_code}")
            return {}

        data = resp.json()
        zones = data.get("data", [])

        result = {}
        for zone in zones:
            name = zone.get("name", "").lower()
            zone_id = zone.get("id")
            # Look for External/WAN zone and Internal/LAN zone
            if "external" in name or "wan" in name or "internet" in name:
                result["external"] = zone_id
            elif "internal" in name or "lan" in name or "default" in name:
                result["internal"] = zone_id

        # If we didn't find named zones, use first two
        if not result and len(zones) >= 2:
            result["external"] = zones[0].get("id")
            result["internal"] = zones[1].get("id")

        return result

    async def _get_or_create_firewall_policy(self, client: httpx.AsyncClient, site_uuid: str, list_id: str) -> str | None:
        """Ensure a firewall policy exists that blocks traffic from the IP list."""
        policy_name = self._get_policy_name()

        # List existing firewall policies
        resp = await client.get(
            f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/firewall/policies",
            headers=self._get_headers(),
        )
        if resp.status_code != 200:
            logger.error(f"UniFi: failed to list firewall policies: HTTP {resp.status_code}")
            return None

        data = resp.json()
        policies = data.get("data", [])

        # Check if policy already exists
        for policy in policies:
            if policy.get("name") == policy_name:
                logger.info(f"UniFi: firewall policy '{policy_name}' already exists")
                return policy.get("id")

        # Get firewall zones
        zones = await self._get_firewall_zones(client, site_uuid)
        if not zones.get("external"):
            logger.error("UniFi: could not find External/WAN firewall zone")
            return None

        # Create new firewall policy - block traffic from our IP list coming from external zone
        policy_payload = {
            "enabled": True,
            "name": policy_name,
            "description": "Automatically block threat IPs detected by Ghostwire Proxy",
            "action": {"type": "BLOCK"},
            "source": {
                "zoneId": zones["external"],
                "trafficFilter": {
                    "type": "IP_ADDRESS",
                    "ipAddressFilter": {
                        "type": "TRAFFIC_MATCHING_LIST",
                        "matchOpposite": False,
                        "trafficMatchingListId": list_id,
                    },
                },
            },
            "destination": {
                "zoneId": zones.get("internal", zones["external"]),  # Fallback to external if no internal
            },
            "ipProtocolScope": {"ipVersion": "IPV4"},
            "loggingEnabled": True,
        }

        logger.info(f"UniFi: creating firewall policy: {policy_payload}")

        resp = await client.post(
            f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/firewall/policies",
            headers=self._get_headers(),
            json=policy_payload,
        )

        if resp.status_code in (200, 201):
            data = resp.json()
            policy_id = data.get("id")
            if policy_id:
                logger.info(f"UniFi: created firewall policy '{policy_name}' (ID: {policy_id})")
                return policy_id

        logger.error(f"UniFi: failed to create firewall policy: {resp.status_code} - {resp.text}")
        return None

    async def ensure_firewall_rule(self) -> dict:
        """Public method to ensure the firewall policy exists. Returns status dict."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=20) as client:
                site_uuid = await self._get_site_uuid(client)
                if not site_uuid:
                    return {"success": False, "error": "Could not get site UUID"}

                list_id = await self._get_or_create_traffic_matching_list(client, site_uuid)
                if not list_id:
                    return {"success": False, "error": "Could not get or create traffic matching list"}

                policy_id = await self._get_or_create_firewall_policy(client, site_uuid, list_id)
                if not policy_id:
                    return {"success": False, "error": "Could not get or create firewall policy"}

                return {
                    "success": True,
                    "list_id": list_id,
                    "policy_id": policy_id,
                    "message": f"Firewall policy '{self._get_policy_name()}' is active"
                }
        except Exception as e:
            logger.error(f"UniFi ensure_firewall_rule failed: {e}")
            return {"success": False, "error": str(e)}

    async def add_to_blocklist(self, ip: str, comment: str = "") -> bool:
        """Add IP to UniFi traffic matching list and ensure blocking policy exists."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=20) as client:
                site_uuid = await self._get_site_uuid(client)
                if not site_uuid:
                    logger.error("UniFi: could not get site UUID")
                    return False

                list_id = await self._get_or_create_traffic_matching_list(client, site_uuid)
                if not list_id:
                    logger.error("UniFi: could not get or create traffic matching list")
                    return False

                # Ensure firewall policy exists
                policy_id = await self._get_or_create_firewall_policy(client, site_uuid, list_id)
                if not policy_id:
                    logger.warning("UniFi: could not ensure firewall policy exists - IPs added but may not be blocked")

                # Get current list items
                current_list = await self._get_traffic_matching_list(client, site_uuid, list_id)
                if not current_list:
                    logger.error("UniFi: could not fetch traffic matching list")
                    return False

                items = current_list.get("items", [])
                existing_ips = [item.get("value") for item in items if item.get("type") == "IP_ADDRESS"]

                if ip in existing_ips:
                    logger.info(f"UniFi: IP {ip} already in blocklist")
                    return True

                # Add new IP to items
                items.append({"type": "IP_ADDRESS", "value": ip})

                # Update the list
                resp = await client.put(
                    f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/traffic-matching-lists/{list_id}",
                    headers=self._get_headers(),
                    json={
                        "type": "IPV4_ADDRESSES",
                        "name": self._get_list_name(),
                        "items": items,
                    },
                )
                if resp.status_code == 200:
                    logger.info(f"UniFi: added IP {ip} to blocklist")
                    return True

                logger.error(f"UniFi add_to_blocklist: HTTP {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"UniFi add_to_blocklist failed: {e}")
            return False

    async def remove_from_blocklist(self, ip: str) -> bool:
        """Remove IP from UniFi traffic matching list."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                site_uuid = await self._get_site_uuid(client)
                if not site_uuid:
                    return False

                list_id = await self._get_or_create_traffic_matching_list(client, site_uuid)
                if not list_id:
                    return False

                # Get current list items
                current_list = await self._get_traffic_matching_list(client, site_uuid, list_id)
                if not current_list:
                    return False

                items = current_list.get("items", [])
                new_items = [item for item in items if item.get("value") != ip]

                if len(new_items) == len(items):
                    logger.warning(f"UniFi: IP {ip} not in blocklist")
                    return True

                # Ensure at least one item (can't be empty)
                if not new_items:
                    new_items = [{"type": "IP_ADDRESS", "value": "192.0.2.1"}]  # TEST-NET-1 placeholder

                # Update the list
                resp = await client.put(
                    f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/traffic-matching-lists/{list_id}",
                    headers=self._get_headers(),
                    json={
                        "type": "IPV4_ADDRESSES",
                        "name": self._get_list_name(),
                        "items": new_items,
                    },
                )
                if resp.status_code == 200:
                    logger.info(f"UniFi: removed IP {ip} from blocklist")
                    return True

                logger.error(f"UniFi remove_from_blocklist: HTTP {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"UniFi remove_from_blocklist failed: {e}")
            return False

    async def get_blocklist(self) -> list[str]:
        """Get list of blocked IPs from traffic matching list."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                site_uuid = await self._get_site_uuid(client)
                if not site_uuid:
                    return []

                list_id = await self._get_or_create_traffic_matching_list(client, site_uuid)
                if not list_id:
                    return []

                current_list = await self._get_traffic_matching_list(client, site_uuid, list_id)
                if current_list:
                    items = current_list.get("items", [])
                    return [item.get("value") for item in items if item.get("type") == "IP_ADDRESS" and item.get("value") != "192.0.2.1"]
                return []
        except Exception as e:
            logger.error(f"UniFi get_blocklist failed: {e}")
            return []


class PfSenseConnector(BaseFirewallConnector):
    """pfSense REST API connector (requires pfSense API package)."""

    def _get_base_url(self) -> str:
        port = self.port or 443
        return f"https://{self.host}:{port}/api/v1"

    def _get_headers(self) -> dict:
        api_key = decrypt_data(self.connector.api_key) if self.connector.api_key else ""
        return {
            "Authorization": api_key,
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                resp = await client.get(
                    f"{self._get_base_url()}/system/version",
                    headers=self._get_headers(),
                )
                if resp.status_code == 200:
                    return {"success": True, "info": "Connected to pfSense"}
                return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def add_to_blocklist(self, ip: str, comment: str = "") -> bool:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                resp = await client.post(
                    f"{self._get_base_url()}/firewall/alias/entry",
                    headers=self._get_headers(),
                    json={
                        "name": self.connector.address_list_name or "ghostwire_blocked",
                        "address": [ip],
                        "detail": [comment or "Blocked by Ghostwire Proxy"],
                    },
                )
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.error(f"pfSense add_to_blocklist failed: {e}")
            return False

    async def remove_from_blocklist(self, ip: str) -> bool:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                resp = await client.delete(
                    f"{self._get_base_url()}/firewall/alias/entry",
                    headers=self._get_headers(),
                    json={
                        "name": self.connector.address_list_name or "ghostwire_blocked",
                        "address": [ip],
                    },
                )
                return resp.status_code in (200, 204)
        except Exception as e:
            logger.error(f"pfSense remove_from_blocklist failed: {e}")
            return False

    async def get_blocklist(self) -> list[str]:
        return []


class OPNsenseConnector(BaseFirewallConnector):
    """OPNsense REST API connector."""

    def _get_base_url(self) -> str:
        port = self.port or 443
        return f"https://{self.host}:{port}/api"

    def _get_auth(self) -> tuple[str, str]:
        api_key = decrypt_data(self.connector.api_key) if self.connector.api_key else ""
        password = decrypt_data(self.connector.password) if self.connector.password else ""
        return (api_key, password)

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                resp = await client.get(
                    f"{self._get_base_url()}/core/firmware/status",
                    auth=self._get_auth(),
                )
                if resp.status_code == 200:
                    return {"success": True, "info": "Connected to OPNsense"}
                return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def add_to_blocklist(self, ip: str, comment: str = "") -> bool:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                alias_name = self.connector.address_list_name or "ghostwire_blocked"
                resp = await client.post(
                    f"{self._get_base_url()}/firewall/alias_util/add/{alias_name}",
                    auth=self._get_auth(),
                    json={"address": ip},
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"OPNsense add_to_blocklist failed: {e}")
            return False

    async def remove_from_blocklist(self, ip: str) -> bool:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                alias_name = self.connector.address_list_name or "ghostwire_blocked"
                resp = await client.post(
                    f"{self._get_base_url()}/firewall/alias_util/delete/{alias_name}",
                    auth=self._get_auth(),
                    json={"address": ip},
                )
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"OPNsense remove_from_blocklist failed: {e}")
            return False

    async def get_blocklist(self) -> list[str]:
        return []


def get_connector(connector: FirewallConnector) -> BaseFirewallConnector:
    """Factory to get the appropriate connector instance."""
    connectors = {
        "routeros": RouterOSConnector,
        "unifi": UniFiConnector,
        "pfsense": PfSenseConnector,
        "opnsense": OPNsenseConnector,
    }
    cls = connectors.get(connector.connector_type)
    if not cls:
        raise ValueError(f"Unknown connector type: {connector.connector_type}")
    return cls(connector)


async def sync_blocklist(db: AsyncSession, connector_id: Optional[str] = None) -> dict:
    """Sync pending blocklist entries to firewalls."""
    # Get pending entries
    query = select(FirewallBlocklist).where(FirewallBlocklist.status == "pending")
    if connector_id:
        query = query.where(FirewallBlocklist.connector_id == connector_id)

    result = await db.execute(query)
    pending = result.scalars().all()

    if not pending:
        return {"synced": 0, "failed": 0}

    # Get all enabled connectors
    conn_query = select(FirewallConnector).where(FirewallConnector.enabled == True)
    if connector_id:
        conn_query = conn_query.where(FirewallConnector.id == connector_id)

    result = await db.execute(conn_query)
    connectors = result.scalars().all()

    synced = 0
    failed = 0
    now = datetime.now(timezone.utc)

    for entry in pending:
        for connector in connectors:
            try:
                fw = get_connector(connector)
                success = await fw.add_to_blocklist(
                    entry.ip_address,
                    f"Threat actor - score: {entry.threat_actor_id}",
                )
                if success:
                    entry.status = "pushed"
                    entry.pushed_at = now
                    entry.connector_id = connector.id
                    connector.last_sync_at = now
                    synced += 1
                else:
                    entry.status = "pending"
                    entry.error_message = f"Failed to push to {connector.name}"
                    failed += 1
            except Exception as e:
                entry.error_message = str(e)
                failed += 1

    await db.commit()
    return {"synced": synced, "failed": failed}
