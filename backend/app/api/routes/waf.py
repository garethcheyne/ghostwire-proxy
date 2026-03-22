"""WAF rules and threat management API routes."""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timezone, timedelta

from app.core.database import get_db
from app.models.user import User
from app.models.waf import WafRule, WafRuleSet, ThreatEvent, ThreatActor, ThreatThreshold
from app.models.audit_log import AuditLog
from app.schemas.waf import (
    WafRuleCreate, WafRuleUpdate, WafRuleResponse,
    WafRuleSetCreate, WafRuleSetUpdate, WafRuleSetResponse,
    ThreatEventResponse, ThreatActorResponse, ThreatActorUpdate,
    ThreatThresholdCreate, ThreatThresholdUpdate, ThreatThresholdResponse,
    ThreatStatsResponse,
)
from app.api.deps import get_current_user

router = APIRouter()


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
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
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
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
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
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
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
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
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

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(actor, field, value)
    actor.updated_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="threat_actor_updated",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated threat actor: {ip}",
    ))
    await db.commit()
    await db.refresh(actor)
    return actor


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
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Manually blocked IP: {ip}",
    ))
    await db.commit()
    return {"status": "blocked", "ip": ip}


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
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Unblocked IP: {ip}",
    ))
    await db.commit()
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
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
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
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
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
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted threat threshold: {threshold.name}",
    ))
    await db.delete(threshold)
    await db.commit()
