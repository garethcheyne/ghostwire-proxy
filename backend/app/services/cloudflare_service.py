"""
Cloudflare API integration service.
Manages DNS records for domains configured in proxy hosts.
"""
import httpx
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.security import decrypt_data
from app.models.dns_provider import DnsProvider, DnsZone


CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareClient:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    async def verify_token(self) -> tuple[bool, Optional[str]]:
        """Verify that the API token is valid"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{CLOUDFLARE_API_BASE}/user/tokens/verify",
                    headers=self.headers,
                    timeout=10.0
                )
                data = response.json()
                if data.get("success"):
                    return True, None
                return False, data.get("errors", [{}])[0].get("message", "Unknown error")
            except Exception as e:
                return False, str(e)

    async def list_zones(self) -> tuple[bool, list | str]:
        """List all DNS zones (domains) in the account"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{CLOUDFLARE_API_BASE}/zones",
                    headers=self.headers,
                    params={"per_page": 50},
                    timeout=10.0
                )
                data = response.json()
                if data.get("success"):
                    return True, data.get("result", [])
                return False, data.get("errors", [{}])[0].get("message", "Unknown error")
            except Exception as e:
                return False, str(e)

    async def get_zone(self, zone_id: str) -> tuple[bool, dict | str]:
        """Get a specific zone by ID"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{CLOUDFLARE_API_BASE}/zones/{zone_id}",
                    headers=self.headers,
                    timeout=10.0
                )
                data = response.json()
                if data.get("success"):
                    return True, data.get("result", {})
                return False, data.get("errors", [{}])[0].get("message", "Unknown error")
            except Exception as e:
                return False, str(e)

    async def list_dns_records(self, zone_id: str, record_type: str = None, name: str = None) -> tuple[bool, list | str]:
        """List DNS records for a zone"""
        async with httpx.AsyncClient() as client:
            try:
                params = {"per_page": 100}
                if record_type:
                    params["type"] = record_type
                if name:
                    params["name"] = name

                response = await client.get(
                    f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/dns_records",
                    headers=self.headers,
                    params=params,
                    timeout=10.0
                )
                data = response.json()
                if data.get("success"):
                    return True, data.get("result", [])
                return False, data.get("errors", [{}])[0].get("message", "Unknown error")
            except Exception as e:
                return False, str(e)

    async def create_dns_record(
        self,
        zone_id: str,
        record_type: str,
        name: str,
        content: str,
        ttl: int = 1,  # 1 = auto
        proxied: bool = True,
    ) -> tuple[bool, dict | str]:
        """Create a new DNS record"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/dns_records",
                    headers=self.headers,
                    json={
                        "type": record_type,
                        "name": name,
                        "content": content,
                        "ttl": ttl,
                        "proxied": proxied,
                    },
                    timeout=10.0
                )
                data = response.json()
                if data.get("success"):
                    return True, data.get("result", {})
                return False, data.get("errors", [{}])[0].get("message", "Unknown error")
            except Exception as e:
                return False, str(e)

    async def update_dns_record(
        self,
        zone_id: str,
        record_id: str,
        record_type: str,
        name: str,
        content: str,
        ttl: int = 1,
        proxied: bool = True,
    ) -> tuple[bool, dict | str]:
        """Update an existing DNS record"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/dns_records/{record_id}",
                    headers=self.headers,
                    json={
                        "type": record_type,
                        "name": name,
                        "content": content,
                        "ttl": ttl,
                        "proxied": proxied,
                    },
                    timeout=10.0
                )
                data = response.json()
                if data.get("success"):
                    return True, data.get("result", {})
                return False, data.get("errors", [{}])[0].get("message", "Unknown error")
            except Exception as e:
                return False, str(e)

    async def delete_dns_record(self, zone_id: str, record_id: str) -> tuple[bool, str]:
        """Delete a DNS record"""
        async with httpx.AsyncClient() as client:
            try:
                response = await client.delete(
                    f"{CLOUDFLARE_API_BASE}/zones/{zone_id}/dns_records/{record_id}",
                    headers=self.headers,
                    timeout=10.0
                )
                data = response.json()
                if data.get("success"):
                    return True, "Deleted"
                return False, data.get("errors", [{}])[0].get("message", "Unknown error")
            except Exception as e:
                return False, str(e)


async def get_cloudflare_client(db: AsyncSession, provider_id: str) -> Optional[CloudflareClient]:
    """Get a Cloudflare client for a provider"""
    result = await db.execute(
        select(DnsProvider).where(
            (DnsProvider.id == provider_id) &
            (DnsProvider.provider_type == "cloudflare") &
            (DnsProvider.enabled == True)
        )
    )
    provider = result.scalar_one_or_none()

    if not provider or not provider.api_key:
        return None

    try:
        api_token = decrypt_data(provider.api_key)
    except Exception:
        api_token = provider.api_key

    return CloudflareClient(api_token)


async def sync_zones(db: AsyncSession, provider_id: str) -> tuple[bool, str]:
    """Sync zones from Cloudflare to local database"""
    client = await get_cloudflare_client(db, provider_id)
    if not client:
        return False, "Provider not found or not configured"

    success, zones_or_error = await client.list_zones()
    if not success:
        return False, zones_or_error

    # Update local zones
    for zone_data in zones_or_error:
        result = await db.execute(
            select(DnsZone).where(
                (DnsZone.provider_id == provider_id) &
                (DnsZone.zone_id == zone_data["id"])
            )
        )
        zone = result.scalar_one_or_none()

        if zone:
            zone.name = zone_data["name"]
            zone.status = zone_data.get("status")
        else:
            zone = DnsZone(
                provider_id=provider_id,
                zone_id=zone_data["id"],
                name=zone_data["name"],
                status=zone_data.get("status"),
            )
            db.add(zone)

    # Update provider last_sync_at
    result = await db.execute(select(DnsProvider).where(DnsProvider.id == provider_id))
    provider = result.scalar_one_or_none()
    if provider:
        from datetime import datetime, timezone
        provider.last_sync_at = datetime.now(timezone.utc)

    await db.commit()
    return True, f"Synced {len(zones_or_error)} zones"


async def check_domain_dns(
    db: AsyncSession,
    provider_id: str,
    domain: str,
    expected_ip: str,
) -> dict:
    """
    Check if a domain has correct DNS configuration.
    Returns status info about the DNS record.
    """
    client = await get_cloudflare_client(db, provider_id)
    if not client:
        return {"status": "error", "message": "Provider not configured"}

    # Find the zone for this domain
    # Domain could be subdomain.example.com, we need to find example.com zone
    parts = domain.split(".")
    zone_name = None
    zone_id = None

    for i in range(len(parts) - 1):
        potential_zone = ".".join(parts[i:])
        result = await db.execute(
            select(DnsZone).where(
                (DnsZone.provider_id == provider_id) &
                (DnsZone.name == potential_zone)
            )
        )
        zone = result.scalar_one_or_none()
        if zone:
            zone_name = zone.name
            zone_id = zone.zone_id
            break

    if not zone_id:
        return {"status": "no_zone", "message": f"No zone found for {domain}"}

    # Check DNS records
    success, records_or_error = await client.list_dns_records(zone_id, name=domain)
    if not success:
        return {"status": "error", "message": records_or_error}

    # Find A or CNAME record
    for record in records_or_error:
        if record["name"] == domain:
            if record["type"] == "A":
                if record["content"] == expected_ip:
                    return {
                        "status": "correct",
                        "record_id": record["id"],
                        "type": "A",
                        "content": record["content"],
                        "proxied": record.get("proxied", False),
                        "zone_id": zone_id,
                    }
                else:
                    return {
                        "status": "mismatch",
                        "record_id": record["id"],
                        "type": "A",
                        "current_content": record["content"],
                        "expected_content": expected_ip,
                        "proxied": record.get("proxied", False),
                        "zone_id": zone_id,
                    }
            elif record["type"] == "CNAME":
                return {
                    "status": "cname",
                    "record_id": record["id"],
                    "type": "CNAME",
                    "content": record["content"],
                    "proxied": record.get("proxied", False),
                    "zone_id": zone_id,
                }

    return {
        "status": "missing",
        "message": f"No A or CNAME record found for {domain}",
        "zone_id": zone_id,
        "zone_name": zone_name,
    }
