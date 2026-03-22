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
    """Ubiquiti UniFi Network Application API connector (API Key auth)."""

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

    async def test_connection(self) -> dict:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                # Use the new integration API to list sites
                resp = await client.get(
                    f"{self._get_base_url()}/proxy/network/integration/v1/sites",
                    headers=self._get_headers(),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Handle paginated response format
                    if isinstance(data, dict) and "data" in data:
                        sites = data.get("data", [])
                        site_count = data.get("totalCount", len(sites))
                        site_names = [s.get("name", "Unknown") for s in sites[:3]]
                        return {"success": True, "info": f"Connected to UniFi ({site_count} site(s): {', '.join(site_names)})"}
                    elif isinstance(data, list):
                        return {"success": True, "info": f"Connected to UniFi ({len(data)} site(s))"}
                    return {"success": True, "info": "Connected to UniFi"}
                elif resp.status_code == 401:
                    return {"success": False, "error": "Invalid API key"}
                elif resp.status_code == 403:
                    return {"success": False, "error": "API key lacks permission"}
                return {"success": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_site_name(self) -> str:
        """Get the site name for the old-style API (default: 'default')."""
        return self.connector.site_id or "default"

    def _get_group_name(self) -> str:
        """Get the firewall group name to use for blocked IPs."""
        return self.connector.address_list_name or "Ghostwire Blocked"

    async def _get_or_create_firewall_group(self, client: httpx.AsyncClient) -> str | None:
        """Get the firewall group ID, creating it if it doesn't exist."""
        site = self._get_site_name()
        group_name = self._get_group_name()

        # List existing groups
        resp = await client.get(
            f"{self._get_base_url()}/proxy/network/api/s/{site}/rest/firewallgroup",
            headers=self._get_headers(),
        )
        if resp.status_code != 200:
            logger.error(f"UniFi: failed to list firewall groups: HTTP {resp.status_code}")
            return None

        data = resp.json()
        groups = data.get("data", [])

        # Find existing group
        for group in groups:
            if group.get("name") == group_name and group.get("group_type") == "address-group":
                return group.get("_id")

        # Create new group if not found
        resp = await client.post(
            f"{self._get_base_url()}/proxy/network/api/s/{site}/rest/firewallgroup",
            headers=self._get_headers(),
            json={
                "name": group_name,
                "group_type": "address-group",
                "group_members": [],
            },
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            if data.get("meta", {}).get("rc") == "ok":
                new_groups = data.get("data", [])
                if new_groups:
                    logger.info(f"UniFi: created firewall group '{group_name}'")
                    return new_groups[0].get("_id")
        logger.error(f"UniFi: failed to create firewall group: {resp.text}")
        return None

    async def _get_firewall_group(self, client: httpx.AsyncClient, group_id: str) -> dict | None:
        """Get firewall group details by ID."""
        site = self._get_site_name()
        resp = await client.get(
            f"{self._get_base_url()}/proxy/network/api/s/{site}/rest/firewallgroup/{group_id}",
            headers=self._get_headers(),
        )
        if resp.status_code == 200:
            data = resp.json()
            groups = data.get("data", [])
            if groups:
                return groups[0]
        return None

    async def add_to_blocklist(self, ip: str, comment: str = "") -> bool:
        """Add IP to UniFi firewall group (address-group)."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                site = self._get_site_name()
                group_id = await self._get_or_create_firewall_group(client)
                if not group_id:
                    logger.error("UniFi: could not get or create firewall group")
                    return False

                # Get current group members
                group = await self._get_firewall_group(client, group_id)
                if not group:
                    logger.error("UniFi: could not fetch firewall group")
                    return False

                members = group.get("group_members", [])
                if ip in members:
                    logger.info(f"UniFi: IP {ip} already in blocklist")
                    return True

                # Add IP to group
                members.append(ip)
                resp = await client.put(
                    f"{self._get_base_url()}/proxy/network/api/s/{site}/rest/firewallgroup/{group_id}",
                    headers=self._get_headers(),
                    json={"group_members": members},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("meta", {}).get("rc") == "ok":
                        return True
                logger.error(f"UniFi add_to_blocklist: HTTP {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"UniFi add_to_blocklist failed: {e}")
            return False

    async def remove_from_blocklist(self, ip: str) -> bool:
        """Remove IP from UniFi firewall group."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                site = self._get_site_name()
                group_id = await self._get_or_create_firewall_group(client)
                if not group_id:
                    return False

                # Get current group members
                group = await self._get_firewall_group(client, group_id)
                if not group:
                    return False

                members = group.get("group_members", [])
                if ip not in members:
                    logger.warning(f"UniFi: IP {ip} not in blocklist")
                    return True  # Already not there

                # Remove IP from group
                members.remove(ip)
                resp = await client.put(
                    f"{self._get_base_url()}/proxy/network/api/s/{site}/rest/firewallgroup/{group_id}",
                    headers=self._get_headers(),
                    json={"group_members": members},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("meta", {}).get("rc") == "ok":
                        return True
                logger.error(f"UniFi remove_from_blocklist: HTTP {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"UniFi remove_from_blocklist failed: {e}")
            return False

    async def get_blocklist(self) -> list[str]:
        """Get list of blocked IPs from firewall group."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                group_id = await self._get_or_create_firewall_group(client)
                if not group_id:
                    return []

                group = await self._get_firewall_group(client, group_id)
                if group:
                    return group.get("group_members", [])
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
