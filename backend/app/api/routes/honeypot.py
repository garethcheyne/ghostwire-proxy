"""Honeypot trap management and IP enrichment API routes."""

import json
import logging
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, distinct

from app.core.database import get_db
from app.core.utils import get_client_ip
from app.models.user import User
from app.models.honeypot import HoneypotTrap, HoneypotHit, IpEnrichment
from app.models.audit_log import AuditLog
from app.schemas.honeypot import (
    HoneypotTrapCreate, HoneypotTrapUpdate, HoneypotTrapResponse,
    HoneypotHitResponse, IpEnrichmentResponse, IpLookupRequest,
    HoneypotStatsResponse,
)
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Honeypot Traps CRUD ───────────────────────────────────────

@router.get("/traps", response_model=list[HoneypotTrapResponse])
async def list_traps(
    enabled: bool | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(HoneypotTrap).order_by(HoneypotTrap.hit_count.desc())
    if enabled is not None:
        query = query.where(HoneypotTrap.enabled == enabled)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/traps", response_model=HoneypotTrapResponse, status_code=status.HTTP_201_CREATED)
async def create_trap(
    data: HoneypotTrapCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Ensure path starts with /
    path = data.path if data.path.startswith("/") else f"/{data.path}"

    # Check for duplicate path within the same host scope
    dup_query = select(HoneypotTrap).where(HoneypotTrap.path == path)
    if data.proxy_host_id:
        dup_query = dup_query.where(HoneypotTrap.proxy_host_id == data.proxy_host_id)
    else:
        dup_query = dup_query.where(HoneypotTrap.proxy_host_id.is_(None))
    existing = await db.execute(dup_query)
    if existing.scalar_one_or_none():
        scope = "globally" if not data.proxy_host_id else "for this host"
        raise HTTPException(status_code=409, detail=f"Trap already exists {scope} for path: {path}")

    trap = HoneypotTrap(**data.model_dump())
    trap.path = path
    db.add(trap)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="honeypot_trap_created",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Created honeypot trap: {data.name} ({path})",
    ))
    await db.commit()
    await db.refresh(trap)

    # Notify nginx to reload honeypot paths
    await _notify_nginx_reload()
    return trap


@router.get("/traps/{trap_id}", response_model=HoneypotTrapResponse)
async def get_trap(
    trap_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(HoneypotTrap).where(HoneypotTrap.id == trap_id))
    trap = result.scalar_one_or_none()
    if not trap:
        raise HTTPException(status_code=404, detail="Honeypot trap not found")
    return trap


@router.put("/traps/{trap_id}", response_model=HoneypotTrapResponse)
async def update_trap(
    trap_id: str,
    data: HoneypotTrapUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(HoneypotTrap).where(HoneypotTrap.id == trap_id))
    trap = result.scalar_one_or_none()
    if not trap:
        raise HTTPException(status_code=404, detail="Honeypot trap not found")

    update_data = data.model_dump(exclude_unset=True)
    if "path" in update_data:
        path = update_data["path"]
        update_data["path"] = path if path.startswith("/") else f"/{path}"

    for field, value in update_data.items():
        setattr(trap, field, value)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="honeypot_trap_updated",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated honeypot trap: {trap.name}",
    ))
    await db.commit()
    await db.refresh(trap)

    await _notify_nginx_reload()
    return trap


@router.delete("/traps/{trap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trap(
    trap_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(HoneypotTrap).where(HoneypotTrap.id == trap_id))
    trap = result.scalar_one_or_none()
    if not trap:
        raise HTTPException(status_code=404, detail="Honeypot trap not found")

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="honeypot_trap_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted honeypot trap: {trap.name} ({trap.path})",
    ))
    await db.delete(trap)
    await db.commit()

    await _notify_nginx_reload()


# ── Honeypot Hits ──────────────────────────────────────────────

@router.get("/hits", response_model=list[HoneypotHitResponse])
async def list_hits(
    trap_id: str | None = None,
    client_ip: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(HoneypotHit).order_by(HoneypotHit.timestamp.desc())
    if trap_id:
        query = query.where(HoneypotHit.trap_id == trap_id)
    if client_ip:
        query = query.where(HoneypotHit.client_ip == client_ip)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


# ── IP Enrichment ──────────────────────────────────────────────

@router.get("/enrich/{ip}", response_model=IpEnrichmentResponse)
async def get_ip_enrichment(
    ip: str,
    force: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Look up full intelligence on an IP address.

    Returns cached data if available. Pass ?force=true to re-fetch.
    """
    from app.services.enrichment_service import enrich_ip

    # Get optional AbuseIPDB key from settings
    from app.models.setting import Setting
    abuseipdb_key = None
    result = await db.execute(
        select(Setting).where(Setting.key == "abuseipdb_api_key")
    )
    setting = result.scalar_one_or_none()
    if setting and setting.value:
        abuseipdb_key = setting.value

    enrichment = await enrich_ip(db, ip, force=force, abuseipdb_key=abuseipdb_key)
    return enrichment


@router.get("/enrichments", response_model=list[IpEnrichmentResponse])
async def list_enrichments(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all enriched IPs, most recent first."""
    result = await db.execute(
        select(IpEnrichment)
        .order_by(IpEnrichment.enriched_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


# ── Honeypot Stats ─────────────────────────────────────────────

@router.get("/stats", response_model=HoneypotStatsResponse)
async def get_honeypot_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    # Trap counts
    total_traps = (await db.execute(select(func.count(HoneypotTrap.id)))).scalar() or 0
    active_traps = (await db.execute(
        select(func.count(HoneypotTrap.id)).where(HoneypotTrap.enabled == True)
    )).scalar() or 0

    # Hit counts
    total_hits = (await db.execute(select(func.count(HoneypotHit.id)))).scalar() or 0
    hits_today = (await db.execute(
        select(func.count(HoneypotHit.id)).where(HoneypotHit.timestamp >= today_start)
    )).scalar() or 0
    hits_this_week = (await db.execute(
        select(func.count(HoneypotHit.id)).where(HoneypotHit.timestamp >= week_start)
    )).scalar() or 0

    # Unique IPs
    unique_ips = (await db.execute(
        select(func.count(distinct(HoneypotHit.client_ip)))
    )).scalar() or 0

    # Auto-blocked count
    auto_blocked = (await db.execute(
        select(func.count(HoneypotHit.id)).where(HoneypotHit.action_taken == "blocked")
    )).scalar() or 0

    # Top traps by hit count
    top_traps_result = await db.execute(
        select(HoneypotTrap.path, HoneypotTrap.hit_count)
        .where(HoneypotTrap.hit_count > 0)
        .order_by(HoneypotTrap.hit_count.desc())
        .limit(10)
    )
    top_traps = [{"path": r[0], "hit_count": r[1]} for r in top_traps_result.all()]

    # Top attackers
    top_attackers_result = await db.execute(
        select(
            HoneypotHit.client_ip,
            func.count(HoneypotHit.id).label("hits"),
            func.max(HoneypotHit.country_code).label("country"),
        )
        .group_by(HoneypotHit.client_ip)
        .order_by(func.count(HoneypotHit.id).desc())
        .limit(10)
    )
    top_attackers = [
        {"ip": r[0], "hits": r[1], "country": r[2]} for r in top_attackers_result.all()
    ]

    # Recent hits
    recent_result = await db.execute(
        select(HoneypotHit)
        .order_by(HoneypotHit.timestamp.desc())
        .limit(10)
    )
    recent_hits = [
        {
            "ip": h.client_ip,
            "path": h.trap_path,
            "timestamp": h.timestamp.isoformat() if h.timestamp else None,
            "country": h.country_code,
            "user_agent": h.user_agent,
        }
        for h in recent_result.scalars().all()
    ]

    return HoneypotStatsResponse(
        total_traps=total_traps,
        active_traps=active_traps,
        total_hits=total_hits,
        hits_today=hits_today,
        hits_this_week=hits_this_week,
        unique_ips=unique_ips,
        auto_blocked=auto_blocked,
        top_traps=top_traps,
        top_attackers=top_attackers,
        recent_hits=recent_hits,
    )


# ── Preset Traps ───────────────────────────────────────────────

@router.post("/traps/install-defaults", status_code=status.HTTP_201_CREATED)
async def install_default_traps(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Install a curated set of default honeypot traps for common scanner targets."""
    defaults = [
        {
            "path": "/wp-login.php",
            "name": "WordPress Login",
            "trap_type": "wordpress",
            "severity": "high",
            "description": "Catches WordPress login scanners",
        },
        {
            "path": "/wp-admin/",
            "name": "WordPress Admin",
            "trap_type": "wordpress",
            "severity": "high",
            "description": "Catches WordPress admin directory scanners",
        },
        {
            "path": "/xmlrpc.php",
            "name": "WordPress XML-RPC",
            "trap_type": "wordpress",
            "severity": "high",
            "description": "Catches XML-RPC brute force attempts",
        },
        {
            "path": "/phpmyadmin/",
            "name": "phpMyAdmin",
            "trap_type": "phpmyadmin",
            "severity": "critical",
            "description": "Catches phpMyAdmin scanners",
        },
        {
            "path": "/pma/",
            "name": "phpMyAdmin (alt)",
            "trap_type": "phpmyadmin",
            "severity": "critical",
            "description": "Catches alternative phpMyAdmin path scanners",
        },
        {
            "path": "/.env",
            "name": "Environment File",
            "trap_type": "generic",
            "severity": "critical",
            "description": "Catches scanners looking for exposed .env files",
        },
        {
            "path": "/.git/config",
            "name": "Git Config",
            "trap_type": "generic",
            "severity": "critical",
            "description": "Catches scanners looking for exposed Git repos",
        },
        {
            "path": "/admin/",
            "name": "Admin Panel",
            "trap_type": "admin",
            "severity": "high",
            "description": "Catches generic admin panel scanners",
        },
        {
            "path": "/administrator/",
            "name": "Joomla Admin",
            "trap_type": "admin",
            "severity": "high",
            "description": "Catches Joomla admin scanners",
        },
        {
            "path": "/api/v1/admin",
            "name": "API Admin Endpoint",
            "trap_type": "api",
            "severity": "high",
            "description": "Catches API admin endpoint scanners",
        },
        {
            "path": "/actuator/env",
            "name": "Spring Boot Actuator",
            "trap_type": "api",
            "severity": "critical",
            "description": "Catches Spring Boot actuator scanners",
        },
        {
            "path": "/debug/vars",
            "name": "Debug Variables",
            "trap_type": "api",
            "severity": "critical",
            "description": "Catches debug endpoint scanners",
        },
        {
            "path": "/config.json",
            "name": "Config JSON",
            "trap_type": "generic",
            "severity": "high",
            "description": "Catches config file scanners",
        },
        {
            "path": "/backup.sql",
            "name": "SQL Backup",
            "trap_type": "generic",
            "severity": "critical",
            "description": "Catches database backup scanners",
        },
        {
            "path": "/shell",
            "name": "Web Shell",
            "trap_type": "generic",
            "severity": "critical",
            "description": "Catches web shell scanners",
        },
        {
            "path": "/cgi-bin/test-cgi",
            "name": "CGI Scanner",
            "trap_type": "generic",
            "severity": "high",
            "description": "Catches CGI vulnerability scanners",
        },
    ]

    installed = []
    for trap_data in defaults:
        existing = await db.execute(
            select(HoneypotTrap).where(HoneypotTrap.path == trap_data["path"])
        )
        if existing.scalar_one_or_none():
            continue

        trap = HoneypotTrap(
            auto_block=True,
            enabled=True,
            response_code=200,
            **trap_data,
        )
        db.add(trap)
        installed.append(trap_data["path"])

    if installed:
        db.add(AuditLog(
            user_id=current_user.id, email=current_user.email,
            action="honeypot_defaults_installed",
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details=f"Installed {len(installed)} default honeypot traps",
        ))
        await db.commit()
        await _notify_nginx_reload()

    return {"installed": installed, "count": len(installed)}


# ── Helper ─────────────────────────────────────────────────────

import httpx

NGINX_RELOAD_URL = "http://ghostwire-proxy-nginx/reload-rules"


async def _notify_nginx_reload():
    """Tell nginx to reload its rules cache (including honeypot paths)."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.get(NGINX_RELOAD_URL, headers={"Host": "localhost"})
    except Exception as e:
        logger.warning("Could not notify nginx to reload rules: %s", e)
