"""Firewall connector services for RouterOS, UniFi, pfSense, OPNsense."""

import ipaddress
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

    async def add_to_blocklist(self, ip: str, comment: str = "") -> tuple[bool, str]:
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

    async def add_to_blocklist(self, ip: str, comment: str = "") -> tuple[bool, str]:
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
                if resp.status_code in (200, 201):
                    return True, ""
                return False, f"RouterOS HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            logger.error(f"RouterOS add_to_blocklist failed: {e}")
            return False, f"RouterOS: {e}"

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

    def _get_list_base_name(self) -> str:
        """Get the base name for traffic matching lists (without IPv4/IPv6 suffix)."""
        name = self.connector.address_list_name or "Ghostwire Block"
        # Strip existing IPv4/IPv6 suffix if present so we can re-derive
        for suffix in (" IPv4", " IPv6"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        return name

    def _get_list_name_ipv4(self) -> str:
        return f"{self._get_list_base_name()} IPv4"

    def _get_list_name_ipv6(self) -> str:
        return f"{self._get_list_base_name()} IPv6"

    def _get_policy_name_ipv4(self) -> str:
        return "Ghostwire Drop IPv4"

    def _get_policy_name_ipv6(self) -> str:
        return "Ghostwire Drop IPv6"

    @staticmethod
    def _is_ipv6(ip: str) -> bool:
        """Check whether an IP string is IPv6."""
        try:
            return isinstance(ipaddress.ip_address(ip), ipaddress.IPv6Address)
        except ValueError:
            return False

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
        findings: list[dict] = []
        try:
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                # 1. Basic connectivity
                resp = await client.get(
                    f"{self._get_base_url()}/proxy/network/integration/v1/sites",
                    headers=self._get_headers(),
                )
                if resp.status_code == 401:
                    return {"success": False, "error": "Invalid API key", "findings": []}
                if resp.status_code == 403:
                    return {"success": False, "error": "API key lacks permission", "findings": []}
                if resp.status_code != 200:
                    return {"success": False, "error": f"HTTP {resp.status_code}", "findings": []}

                data = resp.json()
                sites = data.get("data", [])
                site_count = data.get("totalCount", len(sites))
                site_names = [s.get("name", "Unknown") for s in sites[:3]]
                findings.append({"item": "API Connection", "status": "ok", "detail": f"{site_count} site(s): {', '.join(site_names)}"})

                # Resolve site UUID
                site_uuid = await self._get_site_uuid(client)
                if not site_uuid:
                    findings.append({"item": "Site", "status": "error", "detail": "Could not resolve site UUID"})
                    return {"success": False, "error": "Could not resolve site UUID", "findings": findings}
                findings.append({"item": "Site UUID", "status": "ok", "detail": site_uuid})

                # 2. Check traffic matching lists
                resp = await client.get(
                    f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/traffic-matching-lists",
                    headers=self._get_headers(),
                )
                existing_lists: dict[str, str] = {}
                if resp.status_code == 200:
                    for lst in resp.json().get("data", []):
                        existing_lists[lst.get("name", "")] = lst.get("type", "")

                for label, name, expected_type in [
                    ("IPv4 Address List", self._get_list_name_ipv4(), "IPV4_ADDRESSES"),
                    ("IPv6 Address List", self._get_list_name_ipv6(), "IPV6_ADDRESSES"),
                ]:
                    if name in existing_lists:
                        findings.append({"item": label, "status": "ok", "detail": f"'{name}' found ({existing_lists[name]})"})
                    else:
                        findings.append({"item": label, "status": "missing", "detail": f"'{name}' not found — will be created on first sync/block"})

                # 3. Check firewall policies
                resp = await client.get(
                    f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/firewall/policies",
                    headers=self._get_headers(),
                )
                existing_policies: set[str] = set()
                if resp.status_code == 200:
                    for pol in resp.json().get("data", []):
                        existing_policies.add(pol.get("name", ""))

                for label, name in [
                    ("IPv4 Drop Policy", self._get_policy_name_ipv4()),
                    ("IPv6 Drop Policy", self._get_policy_name_ipv6()),
                ]:
                    if name in existing_policies:
                        findings.append({"item": label, "status": "ok", "detail": f"'{name}' found"})
                    else:
                        findings.append({"item": label, "status": "missing", "detail": f"'{name}' not found — will be created on first sync/block"})

                # 4. Check firewall zones
                zones = await self._get_firewall_zones(client, site_uuid)
                if zones.get("external"):
                    findings.append({"item": "External Zone", "status": "ok", "detail": "Found"})
                else:
                    findings.append({"item": "External Zone", "status": "warning", "detail": "Not found — policy creation may fail"})

                info = f"Connected to UniFi v1 API ({site_count} site(s): {', '.join(site_names)})"
                return {"success": True, "info": info, "findings": findings}
        except Exception as e:
            return {"success": False, "error": str(e), "findings": findings}

    async def _get_or_create_traffic_matching_list(
        self, client: httpx.AsyncClient, site_uuid: str,
        list_name: str | None = None, list_type: str = "IPV4_ADDRESSES",
    ) -> str | None:
        """Get or create a Traffic Matching List for blocked IPs."""
        if list_name is None:
            list_name = self._get_list_name_ipv4()

        placeholder = (
            "192.0.2.1" if list_type == "IPV4_ADDRESSES" else "2001:db8::1"
        )

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
            if lst.get("name") == list_name and lst.get("type") == list_type:
                logger.info(f"UniFi: found existing traffic matching list '{list_name}'")
                return lst.get("id")

        # Create new list with a placeholder IP (required - can't be empty)
        resp = await client.post(
            f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/traffic-matching-lists",
            headers=self._get_headers(),
            json={
                "type": list_type,
                "name": list_name,
                "items": [{"type": "IP_ADDRESS", "value": placeholder}],
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

    async def _get_or_create_firewall_policy(
        self, client: httpx.AsyncClient, site_uuid: str, list_id: str,
        policy_name: str | None = None, ip_version: str = "IPV4",
    ) -> str | None:
        """Ensure a firewall policy exists that blocks traffic from the IP list."""
        if policy_name is None:
            policy_name = self._get_policy_name_ipv4()

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
            "ipProtocolScope": {"ipVersion": ip_version},
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
        """Public method to ensure both IPv4 and IPv6 firewall policies exist."""
        try:
            async with httpx.AsyncClient(verify=False, timeout=20) as client:
                site_uuid = await self._get_site_uuid(client)
                if not site_uuid:
                    return {"success": False, "error": "Could not get site UUID"}

                results = {}
                for label, list_name, list_type, policy_name, ip_ver in [
                    ("ipv4", self._get_list_name_ipv4(), "IPV4_ADDRESSES", self._get_policy_name_ipv4(), "IPV4"),
                    ("ipv6", self._get_list_name_ipv6(), "IPV6_ADDRESSES", self._get_policy_name_ipv6(), "IPV6"),
                ]:
                    list_id = await self._get_or_create_traffic_matching_list(client, site_uuid, list_name, list_type)
                    if not list_id:
                        results[label] = {"success": False, "error": f"Could not get or create '{list_name}'"}
                        continue
                    policy_id = await self._get_or_create_firewall_policy(client, site_uuid, list_id, policy_name, ip_ver)
                    if not policy_id:
                        results[label] = {"success": False, "error": f"Could not get or create '{policy_name}'"}
                        continue
                    results[label] = {"success": True, "list_id": list_id, "policy_id": policy_id}

                all_ok = all(r.get("success") for r in results.values())
                return {
                    "success": all_ok,
                    "results": results,
                    "message": "IPv4 and IPv6 firewall policies are active" if all_ok else "Some policies failed",
                }
        except Exception as e:
            logger.error(f"UniFi ensure_firewall_rule failed: {e}")
            return {"success": False, "error": str(e)}

    async def add_to_blocklist(self, ip: str, comment: str = "") -> tuple[bool, str]:
        """Add IP to the correct UniFi traffic matching list (IPv4 or IPv6) and ensure blocking policy exists."""
        is_v6 = self._is_ipv6(ip)
        list_name = self._get_list_name_ipv6() if is_v6 else self._get_list_name_ipv4()
        list_type = "IPV6_ADDRESSES" if is_v6 else "IPV4_ADDRESSES"
        policy_name = self._get_policy_name_ipv6() if is_v6 else self._get_policy_name_ipv4()
        ip_version = "IPV6" if is_v6 else "IPV4"

        try:
            async with httpx.AsyncClient(verify=False, timeout=20) as client:
                site_uuid = await self._get_site_uuid(client)
                if not site_uuid:
                    logger.error("UniFi: could not get site UUID")
                    return False, "UniFi: could not get site UUID"

                list_id = await self._get_or_create_traffic_matching_list(client, site_uuid, list_name, list_type)
                if not list_id:
                    logger.error(f"UniFi: could not get or create traffic matching list '{list_name}'")
                    return False, f"UniFi: could not get or create list '{list_name}'"

                # Ensure firewall policy exists
                policy_id = await self._get_or_create_firewall_policy(client, site_uuid, list_id, policy_name, ip_version)
                if not policy_id:
                    logger.warning(f"UniFi: could not ensure firewall policy '{policy_name}' - IPs added but may not be blocked")

                # Get current list items
                current_list = await self._get_traffic_matching_list(client, site_uuid, list_id)
                if not current_list:
                    logger.error("UniFi: could not fetch traffic matching list")
                    return False, "UniFi: could not fetch traffic matching list"

                items = current_list.get("items", [])
                existing_ips = [item.get("value") for item in items if item.get("type") == "IP_ADDRESS"]

                if ip in existing_ips:
                    logger.info(f"UniFi: IP {ip} already in blocklist")
                    return True, ""

                # Add new IP to items
                items.append({"type": "IP_ADDRESS", "value": ip})

                # Update the list
                resp = await client.put(
                    f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/traffic-matching-lists/{list_id}",
                    headers=self._get_headers(),
                    json={
                        "type": list_type,
                        "name": list_name,
                        "items": items,
                    },
                )
                if resp.status_code == 200:
                    logger.info(f"UniFi: added IP {ip} to {list_name}")
                    return True, ""

                msg = f"UniFi HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error(f"UniFi add_to_blocklist: {msg}")
                return False, msg
        except Exception as e:
            logger.error(f"UniFi add_to_blocklist failed: {e}")
            return False, f"UniFi: {e}"

    async def remove_from_blocklist(self, ip: str) -> bool:
        """Remove IP from the correct UniFi traffic matching list."""
        is_v6 = self._is_ipv6(ip)
        list_name = self._get_list_name_ipv6() if is_v6 else self._get_list_name_ipv4()
        list_type = "IPV6_ADDRESSES" if is_v6 else "IPV4_ADDRESSES"
        placeholder = "2001:db8::1" if is_v6 else "192.0.2.1"

        try:
            async with httpx.AsyncClient(verify=False, timeout=15) as client:
                site_uuid = await self._get_site_uuid(client)
                if not site_uuid:
                    return False

                list_id = await self._get_or_create_traffic_matching_list(client, site_uuid, list_name, list_type)
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
                    new_items = [{"type": "IP_ADDRESS", "value": placeholder}]

                # Update the list
                resp = await client.put(
                    f"{self._get_base_url()}/proxy/network/integration/v1/sites/{site_uuid}/traffic-matching-lists/{list_id}",
                    headers=self._get_headers(),
                    json={
                        "type": list_type,
                        "name": list_name,
                        "items": new_items,
                    },
                )
                if resp.status_code == 200:
                    logger.info(f"UniFi: removed IP {ip} from {list_name}")
                    return True

                logger.error(f"UniFi remove_from_blocklist: HTTP {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"UniFi remove_from_blocklist failed: {e}")
            return False

    async def get_blocklist(self) -> list[str]:
        """Get list of blocked IPs from both IPv4 and IPv6 traffic matching lists."""
        all_ips: list[str] = []
        placeholders = {"192.0.2.1", "2001:db8::1"}
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                site_uuid = await self._get_site_uuid(client)
                if not site_uuid:
                    return []

                for list_name, list_type in [
                    (self._get_list_name_ipv4(), "IPV4_ADDRESSES"),
                    (self._get_list_name_ipv6(), "IPV6_ADDRESSES"),
                ]:
                    list_id = await self._get_or_create_traffic_matching_list(client, site_uuid, list_name, list_type)
                    if not list_id:
                        continue
                    current_list = await self._get_traffic_matching_list(client, site_uuid, list_id)
                    if current_list:
                        items = current_list.get("items", [])
                        all_ips.extend(
                            item.get("value")
                            for item in items
                            if item.get("type") == "IP_ADDRESS" and item.get("value") not in placeholders
                        )
                return all_ips
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

    async def add_to_blocklist(self, ip: str, comment: str = "") -> tuple[bool, str]:
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
                if resp.status_code in (200, 201):
                    return True, ""
                return False, f"pfSense HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            logger.error(f"pfSense add_to_blocklist failed: {e}")
            return False, f"pfSense: {e}"

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

    async def add_to_blocklist(self, ip: str, comment: str = "") -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                alias_name = self.connector.address_list_name or "ghostwire_blocked"
                resp = await client.post(
                    f"{self._get_base_url()}/firewall/alias_util/add/{alias_name}",
                    auth=self._get_auth(),
                    json={"address": ip},
                )
                if resp.status_code == 200:
                    return True, ""
                return False, f"OPNsense HTTP {resp.status_code}: {resp.text[:200]}"
        except Exception as e:
            logger.error(f"OPNsense add_to_blocklist failed: {e}")
            return False, f"OPNsense: {e}"

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

                    # Push notification: IP blocked on firewall
                    try:
                        from app.services.push_service import push_service
                        await push_service.notify_ip_blocked(
                            ip=entry.ip_address,
                            reason=f"Blocked on {connector.name} ({connector.connector_type})",
                            duration="firewall ban",
                        )
                    except Exception as push_err:
                        logger.debug(f"Push notification skipped: {push_err}")
                else:
                    entry.status = "pending"
                    entry.error_message = f"Failed to push to {connector.name}"
                    failed += 1
            except Exception as e:
                entry.error_message = str(e)
                failed += 1

    await db.commit()
    return {"synced": synced, "failed": failed}
