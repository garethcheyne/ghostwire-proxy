"""
DNS Provider and Zone Management API Routes
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
import uuid

from ...core.database import get_db
from ...core.security import encrypt_data, decrypt_data
from ...models.dns_provider import DnsProvider, DnsZone
from ...services.cloudflare_service import CloudflareClient
from ..deps import get_current_user, get_current_admin_user
from ...models.user import User


router = APIRouter(prefix="/dns", tags=["dns"])


# Schemas
class DnsProviderCreate(BaseModel):
    name: str
    provider_type: str = "cloudflare"
    api_key: str
    api_email: Optional[str] = None


class DnsProviderResponse(BaseModel):
    id: str
    name: str
    provider_type: str
    enabled: bool
    zones: List[dict]

    class Config:
        from_attributes = True


class DnsRecordCreate(BaseModel):
    type: str
    name: str
    content: str
    ttl: int = 1
    proxied: bool = True


class DnsRecordUpdate(BaseModel):
    type: Optional[str] = None
    name: Optional[str] = None
    content: Optional[str] = None
    ttl: Optional[int] = None
    proxied: Optional[bool] = None


# Provider Routes
@router.get("/providers", response_model=List[DnsProviderResponse])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all DNS providers with their zones"""
    result = await db.execute(select(DnsProvider))
    providers = result.scalars().all()

    response = []
    for provider in providers:
        zones_result = await db.execute(
            select(DnsZone).where(DnsZone.provider_id == provider.id)
        )
        zones = zones_result.scalars().all()

        response.append({
            "id": provider.id,
            "name": provider.name,
            "provider_type": provider.provider_type,
            "enabled": provider.enabled,
            "zones": [
                {
                    "id": z.id,
                    "zone_id": z.zone_id,
                    "domain": z.name,
                    "status": z.status or "active",
                    "records_count": 0,
                }
                for z in zones
            ],
        })

    return response


@router.post("/providers", response_model=DnsProviderResponse)
async def create_provider(
    data: DnsProviderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Add a new DNS provider (e.g., Cloudflare)"""
    zones = []

    # Validate credentials by attempting to fetch zones
    if data.provider_type == "cloudflare":
        client = CloudflareClient(data.api_key)
        success, result = await client.list_zones()
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to validate Cloudflare credentials: {result}",
            )
        zones = result

    provider = DnsProvider(
        id=str(uuid.uuid4()),
        name=data.name,
        provider_type=data.provider_type,
        api_key=encrypt_data(data.api_key),
        email=data.api_email,
        enabled=True,
    )

    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    # Sync zones
    for zone_data in zones:
        zone = DnsZone(
            id=str(uuid.uuid4()),
            provider_id=provider.id,
            zone_id=zone_data["id"],
            name=zone_data["name"],
            status=zone_data.get("status", "active"),
        )
        db.add(zone)

    await db.commit()

    return {
        "id": provider.id,
        "name": provider.name,
        "provider_type": provider.provider_type,
        "enabled": provider.enabled,
        "zones": [
            {
                "id": z["id"],
                "zone_id": z["id"],
                "domain": z["name"],
                "status": z.get("status", "active"),
                "records_count": 0,
            }
            for z in zones
        ],
    }


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Delete a DNS provider"""
    result = await db.execute(select(DnsProvider).where(DnsProvider.id == provider_id))
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Delete zones first
    await db.execute(delete(DnsZone).where(DnsZone.provider_id == provider_id))
    await db.delete(provider)
    await db.commit()

    return {"status": "deleted"}


@router.post("/providers/{provider_id}/sync")
async def sync_zones(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Sync zones from the DNS provider"""
    result = await db.execute(select(DnsProvider).where(DnsProvider.id == provider_id))
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    api_key = decrypt_data(provider.api_key)

    if provider.provider_type == "cloudflare":
        client = CloudflareClient(api_key)
        success, zones = await client.list_zones()

        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to fetch zones: {zones}")

        # Get existing zones
        existing_result = await db.execute(
            select(DnsZone).where(DnsZone.provider_id == provider_id)
        )
        existing_zones = {z.zone_id: z for z in existing_result.scalars().all()}

        for zone_data in zones:
            if zone_data["id"] in existing_zones:
                # Update existing
                existing_zones[zone_data["id"]].status = zone_data.get("status", "active")
            else:
                # Create new
                zone = DnsZone(
                    id=str(uuid.uuid4()),
                    provider_id=provider_id,
                    zone_id=zone_data["id"],
                    name=zone_data["name"],
                    status=zone_data.get("status", "active"),
                )
                db.add(zone)

        await db.commit()

    return {"status": "synced"}


# Zone Routes
@router.get("/zones/{zone_id}/records")
async def list_records(
    zone_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all DNS records in a zone"""
    result = await db.execute(select(DnsZone).where(DnsZone.zone_id == zone_id))
    zone = result.scalar_one_or_none()

    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    # Get provider
    provider_result = await db.execute(
        select(DnsProvider).where(DnsProvider.id == zone.provider_id)
    )
    provider = provider_result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    api_key = decrypt_data(provider.api_key)

    if provider.provider_type == "cloudflare":
        client = CloudflareClient(api_key)
        success, records = await client.list_dns_records(zone_id)

        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to fetch records: {records}")

        return [
            {
                "id": r["id"],
                "type": r["type"],
                "name": r["name"],
                "content": r["content"],
                "ttl": r["ttl"],
                "proxied": r.get("proxied", False),
                "linked_proxy_host_id": None,
            }
            for r in records
        ]

    return []


@router.post("/zones/{zone_id}/records")
async def create_record(
    zone_id: str,
    data: DnsRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Create a new DNS record"""
    result = await db.execute(select(DnsZone).where(DnsZone.zone_id == zone_id))
    zone = result.scalar_one_or_none()

    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    provider_result = await db.execute(
        select(DnsProvider).where(DnsProvider.id == zone.provider_id)
    )
    provider = provider_result.scalar_one_or_none()

    api_key = decrypt_data(provider.api_key)

    if provider.provider_type == "cloudflare":
        client = CloudflareClient(api_key)

        # Handle @ for root domain
        name = data.name
        if name == "@":
            name = zone.name
        elif not name.endswith(zone.name):
            name = f"{name}.{zone.name}"

        success, record = await client.create_dns_record(
            zone_id=zone_id,
            record_type=data.type,
            name=name,
            content=data.content,
            ttl=data.ttl,
            proxied=data.proxied,
        )

        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to create record: {record}")

        return {
            "id": record["id"],
            "type": record["type"],
            "name": record["name"],
            "content": record["content"],
            "ttl": record["ttl"],
            "proxied": record.get("proxied", False),
        }


@router.put("/zones/{zone_id}/records/{record_id}")
async def update_record(
    zone_id: str,
    record_id: str,
    data: DnsRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Update a DNS record"""
    result = await db.execute(select(DnsZone).where(DnsZone.zone_id == zone_id))
    zone = result.scalar_one_or_none()

    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    provider_result = await db.execute(
        select(DnsProvider).where(DnsProvider.id == zone.provider_id)
    )
    provider = provider_result.scalar_one_or_none()

    api_key = decrypt_data(provider.api_key)

    if provider.provider_type == "cloudflare":
        client = CloudflareClient(api_key)

        # Get current record first
        success, records = await client.list_dns_records(zone_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to fetch records")

        current_record = next((r for r in records if r["id"] == record_id), None)
        if not current_record:
            raise HTTPException(status_code=404, detail="Record not found")

        # Use existing values for unset fields
        record_type = data.type or current_record["type"]
        content = data.content or current_record["content"]
        ttl = data.ttl if data.ttl is not None else current_record["ttl"]
        proxied = data.proxied if data.proxied is not None else current_record.get("proxied", False)

        name = data.name or current_record["name"]
        if name == "@":
            name = zone.name
        elif not name.endswith(zone.name):
            name = f"{name}.{zone.name}"

        success, record = await client.update_dns_record(
            zone_id=zone_id,
            record_id=record_id,
            record_type=record_type,
            name=name,
            content=content,
            ttl=ttl,
            proxied=proxied,
        )

        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to update record: {record}")

        return {
            "id": record["id"],
            "type": record["type"],
            "name": record["name"],
            "content": record["content"],
            "ttl": record["ttl"],
            "proxied": record.get("proxied", False),
        }


@router.delete("/zones/{zone_id}/records/{record_id}")
async def delete_record(
    zone_id: str,
    record_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Delete a DNS record"""
    result = await db.execute(select(DnsZone).where(DnsZone.zone_id == zone_id))
    zone = result.scalar_one_or_none()

    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    provider_result = await db.execute(
        select(DnsProvider).where(DnsProvider.id == zone.provider_id)
    )
    provider = provider_result.scalar_one_or_none()

    api_key = decrypt_data(provider.api_key)

    if provider.provider_type == "cloudflare":
        client = CloudflareClient(api_key)
        success, msg = await client.delete_dns_record(zone_id, record_id)

        if not success:
            raise HTTPException(status_code=400, detail=f"Failed to delete record: {msg}")

    return {"status": "deleted"}
