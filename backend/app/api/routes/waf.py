"""WAF rules and threat management API routes."""

import httpx
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, delete as sa_delete
from datetime import datetime, timezone, timedelta

from app.core.database import get_db
from app.core.utils import get_client_ip
from app.models.user import User
from app.models.waf import WafRule, WafRuleSet, ThreatEvent, ThreatActor, ThreatThreshold
from app.models.firewall import FirewallConnector, FirewallBlocklist
from app.models.audit_log import AuditLog
from app.schemas.waf import (
    WafRuleCreate, WafRuleUpdate, WafRuleResponse,
    WafRuleSetCreate, WafRuleSetUpdate, WafRuleSetResponse,
    ThreatEventResponse, ThreatActorResponse, ThreatActorUpdate,
    ThreatThresholdCreate, ThreatThresholdUpdate, ThreatThresholdResponse,
    ThreatStatsResponse,
)
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

NGINX_RELOAD_URL = "http://ghostwire-proxy-nginx/reload-rules"


async def _notify_nginx_reload():
    """Tell nginx to reload its rules cache immediately."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.get(NGINX_RELOAD_URL, headers={"Host": "localhost"})
    except Exception as e:
        logger.warning("Could not notify nginx to reload rules: %s", e)


# ── WAF Rule Sets ──────────────────────────────────────────────

@router.get("/rules/sets", response_model=list[WafRuleSetResponse])
async def list_rule_sets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WafRuleSet).order_by(WafRuleSet.name))
    return result.scalars().all()


@router.post("/rules/sets", response_model=WafRuleSetResponse, status_code=status.HTTP_201_CREATED)
async def create_rule_set(
    data: WafRuleSetCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rule_set = WafRuleSet(**data.model_dump())
    db.add(rule_set)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="waf_rule_set_created",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Created WAF rule set: {data.name}",
    ))
    await db.commit()
    await db.refresh(rule_set)
    return rule_set


# ── WAF Rules ──────────────────────────────────────────────────

@router.get("/rules", response_model=list[WafRuleResponse])
async def list_rules(
    category: str | None = None,
    enabled: bool | None = None,
    proxy_host_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(WafRule).order_by(WafRule.category, WafRule.name)
    if category:
        query = query.where(WafRule.category == category)
    if enabled is not None:
        query = query.where(WafRule.enabled == enabled)
    if proxy_host_id:
        query = query.where(WafRule.proxy_host_id == proxy_host_id)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/rules", response_model=WafRuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    data: WafRuleCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rule = WafRule(**data.model_dump())
    db.add(rule)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="waf_rule_created",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Created WAF rule: {data.name} ({data.category})",
    ))
    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("/rules/{rule_id}", response_model=WafRuleResponse)
async def get_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WafRule).where(WafRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="WAF rule not found")
    return rule


@router.put("/rules/{rule_id}", response_model=WafRuleResponse)
async def update_rule(
    rule_id: str,
    data: WafRuleUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WafRule).where(WafRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="WAF rule not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="waf_rule_updated",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated WAF rule: {rule.name}",
    ))
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(WafRule).where(WafRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="WAF rule not found")

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="waf_rule_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted WAF rule: {rule.name}",
    ))
    await db.delete(rule)
    await db.commit()


# ── Threat Events ──────────────────────────────────────────────

@router.get("/events", response_model=list[ThreatEventResponse])
async def list_threat_events(
    category: str | None = None,
    severity: str | None = None,
    client_ip: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(ThreatEvent).order_by(ThreatEvent.timestamp.desc())
    if category:
        query = query.where(ThreatEvent.category == category)
    if severity:
        query = query.where(ThreatEvent.severity == severity)
    if client_ip:
        query = query.where(ThreatEvent.client_ip == client_ip)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_threat_event(
    event_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single threat event."""
    result = await db.execute(select(ThreatEvent).where(ThreatEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Threat event not found")

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="threat_event_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted threat event {event_id} (IP: {event.client_ip})",
    ))
    await db.delete(event)
    await db.commit()


@router.delete("/events", status_code=status.HTTP_200_OK)
async def purge_threat_events(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Purge all threat events."""
    count_result = await db.execute(select(func.count(ThreatEvent.id)))
    count = count_result.scalar() or 0

    await db.execute(sa_delete(ThreatEvent))

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="threat_events_purged",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Purged all threat events ({count} records)",
    ))
    await db.commit()
    return {"status": "ok", "deleted": count}


@router.get("/threats/geo")
async def get_threat_geo_data(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get threat events grouped by country for map visualization."""
    result = await db.execute(
        select(
            ThreatActor.country_code,
            ThreatActor.country_name,
            func.sum(ThreatActor.total_events).label("count"),
        )
        .where(ThreatActor.country_code.isnot(None))
        .group_by(ThreatActor.country_code, ThreatActor.country_name)
        .order_by(func.sum(ThreatActor.total_events).desc())
    )
    return [
        {"country_code": row[0], "country_name": row[1] or row[0], "count": row[2]}
        for row in result.all()
    ]


@router.get("/threats/by-host")
async def get_threats_by_host(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get threat events grouped by host with category breakdown."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Threats per host
    host_result = await db.execute(
        select(
            ThreatEvent.host,
            func.count(ThreatEvent.id).label("count"),
        )
        .where(and_(ThreatEvent.host.isnot(None), ThreatEvent.timestamp >= since))
        .group_by(ThreatEvent.host)
        .order_by(func.count(ThreatEvent.id).desc())
        .limit(15)
    )
    hosts = host_result.all()

    result = []
    for host, count in hosts:
        # Category breakdown per host
        cat_result = await db.execute(
            select(
                ThreatEvent.category,
                func.count(ThreatEvent.id).label("count"),
            )
            .where(and_(ThreatEvent.host == host, ThreatEvent.timestamp >= since))
            .group_by(ThreatEvent.category)
            .order_by(func.count(ThreatEvent.id).desc())
        )
        categories = {row[0]: row[1] for row in cat_result.all()}
        result.append({
            "host": host,
            "total": count,
            "categories": categories,
        })

    return result


@router.get("/stats", response_model=ThreatStatsResponse)
async def get_threat_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    # Total events
    total = await db.execute(select(func.count(ThreatEvent.id)))
    total_events = total.scalar() or 0

    # Today
    today_result = await db.execute(
        select(func.count(ThreatEvent.id)).where(ThreatEvent.timestamp >= today_start)
    )
    events_today = today_result.scalar() or 0

    # This week
    week_result = await db.execute(
        select(func.count(ThreatEvent.id)).where(ThreatEvent.timestamp >= week_start)
    )
    events_this_week = week_result.scalar() or 0

    # Total actors
    total_actors_result = await db.execute(select(func.count(ThreatActor.id)))
    total_actors = total_actors_result.scalar() or 0

    # Blocked actors
    blocked_result = await db.execute(
        select(func.count(ThreatActor.id)).where(
            ThreatActor.current_status.in_(['temp_blocked', 'perm_blocked', 'firewall_banned'])
        )
    )
    blocked_actors = blocked_result.scalar() or 0

    # Top categories
    cat_result = await db.execute(
        select(ThreatEvent.category, func.count(ThreatEvent.id).label('count'))
        .group_by(ThreatEvent.category)
        .order_by(func.count(ThreatEvent.id).desc())
        .limit(10)
    )
    top_categories = [{"category": r.category, "count": r.count} for r in cat_result.all()]

    # Top actors
    actor_result = await db.execute(
        select(ThreatActor)
        .order_by(ThreatActor.threat_score.desc())
        .limit(10)
    )
    top_actors = [
        {"ip": a.ip_address, "score": a.threat_score, "events": a.total_events, "status": a.current_status}
        for a in actor_result.scalars().all()
    ]

    # Severity breakdown
    sev_result = await db.execute(
        select(ThreatEvent.severity, func.count(ThreatEvent.id).label('count'))
        .group_by(ThreatEvent.severity)
    )
    severity_breakdown = {r.severity: r.count for r in sev_result.all()}

    return ThreatStatsResponse(
        total_events=total_events,
        events_today=events_today,
        events_this_week=events_this_week,
        total_actors=total_actors,
        blocked_actors=blocked_actors,
        top_categories=top_categories,
        top_actors=top_actors,
        severity_breakdown=severity_breakdown,
    )


# ── Threat Actors ──────────────────────────────────────────────

@router.get("/actors", response_model=list[ThreatActorResponse])
async def list_threat_actors(
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(ThreatActor).order_by(ThreatActor.threat_score.desc())
    if status_filter:
        query = query.where(ThreatActor.current_status == status_filter)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/actors/{ip}", response_model=ThreatActorResponse)
async def get_threat_actor(
    ip: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ThreatActor).where(ThreatActor.ip_address == ip))
    actor = result.scalar_one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail="Threat actor not found")
    return actor


@router.put("/actors/{ip}", response_model=ThreatActorResponse)
async def update_threat_actor(
    ip: str,
    data: ThreatActorUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ThreatActor).where(ThreatActor.ip_address == ip))
    actor = result.scalar_one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail="Threat actor not found")

    import json as _json
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "tags":
            setattr(actor, field, _json.dumps(value) if value is not None else None)
        else:
            setattr(actor, field, value)
    actor.updated_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="threat_actor_updated",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated threat actor: {ip}",
    ))
    await db.commit()
    await db.refresh(actor)
    return actor


@router.delete("/actors/{ip}")
async def delete_threat_actor(
    ip: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ThreatActor).where(ThreatActor.ip_address == ip))
    actor = result.scalar_one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail="Threat actor not found")

    actor_id = actor.id
    # Delete associated firewall blocklist entries and threat events
    from app.models.firewall import FirewallBlocklist
    await db.execute(sa_delete(FirewallBlocklist).where(FirewallBlocklist.threat_actor_id == actor_id))
    await db.execute(sa_delete(ThreatEvent).where(ThreatEvent.client_ip == ip))
    await db.delete(actor)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="threat_actor_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted threat actor: {ip}",
    ))
    await db.commit()
    await _notify_nginx_reload()
    return {"status": "deleted", "ip": ip}


@router.post("/actors/bulk-firewall-ban")
async def bulk_firewall_ban(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Push multiple IPs to all enabled firewall connectors in one operation."""
    body = await request.json()
    ips: list[str] = body.get("ips", [])
    if not ips:
        raise HTTPException(status_code=400, detail="No IPs provided")
    if len(ips) > 500:
        raise HTTPException(status_code=400, detail="Maximum 500 IPs per request")

    conn_result = await db.execute(
        select(FirewallConnector).where(FirewallConnector.enabled == True)
    )
    connectors = conn_result.scalars().all()
    if not connectors:
        raise HTTPException(status_code=400, detail="No enabled firewall connectors configured")

    from app.services.firewall_service import get_connector as get_fw_connector

    now = datetime.now(timezone.utc)
    results = []
    total_pushed = 0
    total_errors = []

    for ip in ips:
        result = await db.execute(select(ThreatActor).where(ThreatActor.ip_address == ip))
        actor = result.scalar_one_or_none()
        if not actor:
            actor = ThreatActor(
                ip_address=ip,
                current_status="firewall_banned",
                firewall_banned_at=now,
                perm_blocked_at=now,
                first_seen=now,
                last_seen=now,
            )
            db.add(actor)
            await db.flush()
        else:
            actor.current_status = "firewall_banned"
            actor.firewall_banned_at = now
            if not actor.perm_blocked_at:
                actor.perm_blocked_at = now
            actor.updated_at = now

        pushed = 0
        ip_errors = []
        for connector in connectors:
            existing = await db.execute(
                select(FirewallBlocklist).where(
                    FirewallBlocklist.ip_address == ip,
                    FirewallBlocklist.connector_id == connector.id,
                    FirewallBlocklist.status == "pushed",
                )
            )
            if existing.scalar_one_or_none():
                pushed += 1
                continue

            entry = FirewallBlocklist(
                threat_actor_id=actor.id,
                ip_address=ip,
                connector_id=connector.id,
                status="pending",
            )
            db.add(entry)
            await db.flush()

            try:
                instance = get_fw_connector(connector)
                success = await instance.add_to_blocklist(ip, "Ghostwire bulk firewall ban")
                if success:
                    entry.status = "pushed"
                    entry.pushed_at = now
                    pushed += 1
                else:
                    entry.error_message = "Push failed"
                    ip_errors.append(connector.name)
            except Exception as e:
                entry.error_message = str(e)[:500]
                ip_errors.append(connector.name)

        total_pushed += pushed
        total_errors.extend(ip_errors)
        results.append({"ip": ip, "pushed": pushed, "errors": ip_errors})

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="threat_actors_bulk_firewall_banned",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Bulk firewall banned {len(ips)} IPs (pushed {total_pushed} total)",
    ))
    await db.commit()
    await _notify_nginx_reload()
    return {
        "status": "ok",
        "total_ips": len(ips),
        "total_pushed": total_pushed,
        "total_errors": len(total_errors),
        "results": results,
    }


@router.post("/actors/{ip}/block")
async def block_threat_actor(
    ip: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ThreatActor).where(ThreatActor.ip_address == ip))
    actor = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if not actor:
        actor = ThreatActor(
            ip_address=ip,
            current_status="perm_blocked",
            perm_blocked_at=now,
            first_seen=now,
            last_seen=now,
        )
        db.add(actor)
    else:
        actor.current_status = "perm_blocked"
        actor.perm_blocked_at = now
        actor.updated_at = now

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="threat_actor_blocked",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Manually blocked IP: {ip}",
    ))
    await db.commit()
    await _notify_nginx_reload()
    return {"status": "blocked", "ip": ip}


@router.post("/actors/{ip}/firewall-ban")
async def firewall_ban_threat_actor(
    ip: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Escalate an IP to firewall_banned and push to all enabled firewall connectors."""
    # Check that at least one enabled connector exists
    conn_result = await db.execute(
        select(FirewallConnector).where(FirewallConnector.enabled == True)
    )
    connectors = conn_result.scalars().all()
    if not connectors:
        raise HTTPException(status_code=400, detail="No enabled firewall connectors configured")

    now = datetime.now(timezone.utc)
    result = await db.execute(select(ThreatActor).where(ThreatActor.ip_address == ip))
    actor = result.scalar_one_or_none()

    if not actor:
        actor = ThreatActor(
            ip_address=ip,
            current_status="firewall_banned",
            firewall_banned_at=now,
            perm_blocked_at=now,
            first_seen=now,
            last_seen=now,
        )
        db.add(actor)
        await db.flush()
    else:
        actor.current_status = "firewall_banned"
        actor.firewall_banned_at = now
        if not actor.perm_blocked_at:
            actor.perm_blocked_at = now
        actor.updated_at = now

    # Create blocklist entries for each enabled connector and push
    from app.services.firewall_service import get_connector as get_fw_connector
    pushed = 0
    errors = []
    for connector in connectors:
        # Check if already pushed for this IP + connector
        existing = await db.execute(
            select(FirewallBlocklist).where(
                FirewallBlocklist.ip_address == ip,
                FirewallBlocklist.connector_id == connector.id,
                FirewallBlocklist.status == "pushed",
            )
        )
        if existing.scalar_one_or_none():
            pushed += 1
            continue

        entry = FirewallBlocklist(
            threat_actor_id=actor.id,
            ip_address=ip,
            connector_id=connector.id,
            status="pending",
        )
        db.add(entry)
        await db.flush()

        try:
            instance = get_fw_connector(connector)
            success = await instance.add_to_blocklist(ip, "Ghostwire manual firewall ban")
            if success:
                entry.status = "pushed"
                entry.pushed_at = now
                pushed += 1
            else:
                entry.error_message = "Push failed"
                errors.append(connector.name)
        except Exception as e:
            entry.error_message = str(e)[:500]
            errors.append(connector.name)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="threat_actor_firewall_banned",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Firewall banned IP: {ip} (pushed to {pushed} connector(s))",
    ))
    await db.commit()
    await _notify_nginx_reload()
    return {
        "status": "firewall_banned",
        "ip": ip,
        "pushed": pushed,
        "errors": errors,
    }


@router.post("/actors/{ip}/unblock")
async def unblock_threat_actor(
    ip: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ThreatActor).where(ThreatActor.ip_address == ip))
    actor = result.scalar_one_or_none()
    if not actor:
        raise HTTPException(status_code=404, detail="Threat actor not found")

    actor.current_status = "monitored"
    actor.temp_block_until = None
    actor.perm_blocked_at = None
    actor.firewall_banned_at = None
    actor.updated_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="threat_actor_unblocked",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Unblocked IP: {ip}",
    ))
    await db.commit()
    await _notify_nginx_reload()
    return {"status": "unblocked", "ip": ip}


# ── Threat Thresholds ──────────────────────────────────────────

@router.get("/thresholds", response_model=list[ThreatThresholdResponse])
async def list_thresholds(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ThreatThreshold).order_by(ThreatThreshold.priority.desc())
    )
    return result.scalars().all()


@router.post("/thresholds", response_model=ThreatThresholdResponse, status_code=status.HTTP_201_CREATED)
async def create_threshold(
    data: ThreatThresholdCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    threshold = ThreatThreshold(**data.model_dump())
    db.add(threshold)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="threat_threshold_created",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Created threat threshold: {data.name}",
    ))
    await db.commit()
    await db.refresh(threshold)
    return threshold


@router.put("/thresholds/{threshold_id}", response_model=ThreatThresholdResponse)
async def update_threshold(
    threshold_id: str,
    data: ThreatThresholdUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ThreatThreshold).where(ThreatThreshold.id == threshold_id))
    threshold = result.scalar_one_or_none()
    if not threshold:
        raise HTTPException(status_code=404, detail="Threshold not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(threshold, field, value)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="threat_threshold_updated",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated threat threshold: {threshold.name}",
    ))
    await db.commit()
    await db.refresh(threshold)
    return threshold


@router.delete("/thresholds/{threshold_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_threshold(
    threshold_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ThreatThreshold).where(ThreatThreshold.id == threshold_id))
    threshold = result.scalar_one_or_none()
    if not threshold:
        raise HTTPException(status_code=404, detail="Threshold not found")

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="threat_threshold_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted threat threshold: {threshold.name}",
    ))
    await db.delete(threshold)
    await db.commit()
