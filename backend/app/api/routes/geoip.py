"""GeoIP configuration and rules API routes."""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.utils import get_client_ip
from app.models.user import User
from app.models.rate_limit import GeoipSettings, GeoipRule
from app.models.audit_log import AuditLog
from app.schemas.rate_limit import (
    GeoipSettingsUpdate, GeoipSettingsResponse,
    GeoipRuleCreate, GeoipRuleUpdate, GeoipRuleResponse,
)
from app.api.deps import get_current_user

router = APIRouter()


# ── GeoIP Settings ─────────────────────────────────────────────

@router.get("/settings", response_model=GeoipSettingsResponse | None)
async def get_geoip_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(GeoipSettings).limit(1))
    return result.scalar_one_or_none()


@router.put("/settings", response_model=GeoipSettingsResponse)
async def update_geoip_settings(
    data: GeoipSettingsUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.security import encrypt_data

    result = await db.execute(select(GeoipSettings).limit(1))
    settings_obj = result.scalar_one_or_none()

    update_data = data.model_dump(exclude_unset=True)
    if "license_key" in update_data and update_data["license_key"]:
        update_data["license_key"] = encrypt_data(update_data["license_key"])

    if settings_obj:
        for field, value in update_data.items():
            setattr(settings_obj, field, value)
    else:
        settings_obj = GeoipSettings(
            provider=update_data.get("provider", "maxmind"),
            database_path=update_data.get("database_path"),
            license_key=update_data.get("license_key"),
            auto_update=update_data.get("auto_update", True),
            enabled=update_data.get("enabled", True),
        )
        db.add(settings_obj)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="geoip_settings_updated",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details="Updated GeoIP settings",
    ))
    await db.commit()
    await db.refresh(settings_obj)
    return settings_obj


# ── GeoIP Rules ────────────────────────────────────────────────

@router.get("/rules", response_model=list[GeoipRuleResponse])
async def list_geoip_rules(
    proxy_host_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(GeoipRule).order_by(GeoipRule.name)
    if proxy_host_id:
        query = query.where(GeoipRule.proxy_host_id == proxy_host_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/rules", response_model=GeoipRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_geoip_rule(
    data: GeoipRuleCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rule = GeoipRule(**data.model_dump())
    db.add(rule)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="geoip_rule_created",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Created GeoIP rule: {data.name}",
    ))
    await db.commit()
    await db.refresh(rule)
    return rule


@router.put("/rules/{rule_id}", response_model=GeoipRuleResponse)
async def update_geoip_rule(
    rule_id: str,
    data: GeoipRuleUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(GeoipRule).where(GeoipRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="GeoIP rule not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="geoip_rule_updated",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated GeoIP rule: {rule.name}",
    ))
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_geoip_rule(
    rule_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(GeoipRule).where(GeoipRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="GeoIP rule not found")

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="geoip_rule_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted GeoIP rule: {rule.name}",
    ))
    await db.delete(rule)
    await db.commit()


# ── GeoIP Lookup ───────────────────────────────────────────────

@router.get("/lookup/{ip}")
async def lookup_ip(
    ip: str,
    current_user: User = Depends(get_current_user),
):
    """Lookup geographic information for an IP address."""
    try:
        import geoip2.database
        import os

        db_path = os.environ.get("GEOIP_DB_PATH", "/data/geoip/GeoLite2-Country.mmdb")
        if not os.path.exists(db_path):
            return {"ip": ip, "error": "GeoIP database not available"}

        reader = geoip2.database.Reader(db_path)
        response = reader.country(ip)
        reader.close()

        return {
            "ip": ip,
            "country_code": response.country.iso_code,
            "country_name": response.country.name,
            "continent": response.continent.name,
        }
    except Exception as e:
        return {"ip": ip, "error": str(e)}
