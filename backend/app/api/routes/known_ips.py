"""Known IPs: operator-supplied names for addresses, plus per-IP traffic reports."""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import select, func, and_, or_, literal_column, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone, timedelta
from typing import Optional
import ipaddress

from app.core.database import get_db
from app.core.utils import get_client_ip
from app.models.user import User
from app.models.known_ip import KnownIp
from app.models.traffic_log import TrafficLog
from app.models.proxy_host import ProxyHost
from app.models.waf import ThreatEvent
from app.models.honeypot import IpEnrichment
from app.models.audit_log import AuditLog
from app.api.deps import get_current_user, get_current_admin_user

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class KnownIpBase(BaseModel):
    ip_address: str
    label: str
    category: Optional[str] = None
    notes: Optional[str] = None
    trusted: bool = False

    @field_validator("ip_address")
    @classmethod
    def valid_ip(cls, v: str) -> str:
        v = v.strip()
        try:
            # Normalises "1.2.3.004" and compressed IPv6 to one canonical form,
            # so the same address can't be stored twice under two spellings.
            return str(ipaddress.ip_address(v))
        except ValueError:
            raise ValueError(f"'{v}' is not a valid IP address")

    @field_validator("label")
    @classmethod
    def label_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Label cannot be empty")
        return v


class KnownIpCreate(KnownIpBase):
    pass


class KnownIpUpdate(BaseModel):
    label: Optional[str] = None
    category: Optional[str] = None
    notes: Optional[str] = None
    trusted: Optional[bool] = None


class KnownIpResponse(KnownIpBase):
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[KnownIpResponse])
async def list_known_ips(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = None,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List known IPs, newest first."""
    filters = []
    if category:
        filters.append(KnownIp.category == category)
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(
            KnownIp.ip_address.ilike(term),
            KnownIp.label.ilike(term),
            KnownIp.notes.ilike(term),
        ))

    query = select(KnownIp)
    count_query = select(func.count()).select_from(KnownIp)
    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    total = (await db.execute(count_query)).scalar() or 0
    rows = (await db.execute(
        query.order_by(KnownIp.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all()

    response.headers["X-Total-Count"] = str(int(total))
    return rows


@router.post("/", response_model=KnownIpResponse, status_code=status.HTTP_201_CREATED)
async def create_known_ip(
    payload: KnownIpCreate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(
        select(KnownIp).where(KnownIp.ip_address == payload.ip_address)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{payload.ip_address} is already labelled '{existing.label}'",
        )

    known = KnownIp(**payload.model_dump(), created_by=current_user.id)
    db.add(known)
    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="known_ip_created", ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Labelled {payload.ip_address} as '{payload.label}'",
    ))
    await db.commit()
    await db.refresh(known)
    return known


@router.put("/{known_id}", response_model=KnownIpResponse)
async def update_known_ip(
    known_id: str,
    payload: KnownIpUpdate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    known = (await db.execute(select(KnownIp).where(KnownIp.id == known_id))).scalar_one_or_none()
    if not known:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Known IP not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(known, field, value)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="known_ip_updated", ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated label for {known.ip_address}",
    ))
    await db.commit()
    await db.refresh(known)
    return known


@router.delete("/{known_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_known_ip(
    known_id: str,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    known = (await db.execute(select(KnownIp).where(KnownIp.id == known_id))).scalar_one_or_none()
    if not known:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Known IP not found")

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="known_ip_deleted", ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Removed label for {known.ip_address}",
    ))
    await db.delete(known)
    await db.commit()


# ── Bulk lookup, for annotating grids ────────────────────────────────────────

class LookupRequest(BaseModel):
    ips: list[str]


@router.post("/lookup")
async def lookup_known_ips(
    payload: LookupRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve many addresses at once.

    A grid renders 50 rows; asking per row would be 50 round trips, so the
    client sends the whole visible page in one request.
    """
    ips = [i for i in {ip.strip() for ip in payload.ips} if i][:500]
    if not ips:
        return {}

    rows = (await db.execute(select(KnownIp).where(KnownIp.ip_address.in_(ips)))).scalars().all()
    return {
        r.ip_address: {"label": r.label, "category": r.category, "trusted": r.trusted, "id": r.id}
        for r in rows
    }


# ── Per-IP traffic report ────────────────────────────────────────────────────

@router.get("/report/{ip_address}")
async def get_ip_report(
    ip_address: str,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Everything this proxy knows about one address.

    Works for any IP, not just labelled ones — looking up an address you've just
    seen in a log is the common case, and having to label it first would be
    backwards.
    """
    try:
        ip = str(ipaddress.ip_address(ip_address.strip()))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"'{ip_address}' is not a valid IP address",
        )

    since = datetime.now(timezone.utc) - timedelta(days=days)
    base = and_(TrafficLog.client_ip == ip, TrafficLog.timestamp >= since)

    totals = (await db.execute(
        select(
            func.count(TrafficLog.id).label("requests"),
            func.min(TrafficLog.timestamp).label("first_seen"),
            func.max(TrafficLog.timestamp).label("last_seen"),
            func.sum(TrafficLog.bytes_sent).label("bytes_sent"),
            func.sum(TrafficLog.bytes_received).label("bytes_received"),
            func.count(func.distinct(TrafficLog.request_uri)).label("unique_paths"),
            func.count(func.distinct(TrafficLog.proxy_host_id)).label("hosts_touched"),
            func.avg(TrafficLog.response_time).filter(
                TrafficLog.is_streaming.isnot(True)
            ).label("avg_response_time"),
            func.count(func.nullif(TrafficLog.status >= 400, False)).label("errors"),
            func.count(func.nullif(TrafficLog.is_bot.is_(True), False)).label("bot_requests"),
        ).where(base)
    )).one()

    host_names = {
        h.id: (h.domain_names or [h.id])[0]
        for h in (await db.execute(select(ProxyHost))).scalars().all()
    }

    per_host = (await db.execute(
        select(
            TrafficLog.proxy_host_id,
            func.count(TrafficLog.id).label("requests"),
            func.max(TrafficLog.timestamp).label("last_seen"),
            func.count(func.nullif(TrafficLog.status >= 400, False)).label("errors"),
        ).where(base).group_by(TrafficLog.proxy_host_id)
        .order_by(func.count(TrafficLog.id).desc()).limit(25)
    )).all()

    top_paths = (await db.execute(
        select(
            TrafficLog.request_uri,
            func.count(TrafficLog.id).label("requests"),
            func.max(TrafficLog.status).label("last_status"),
        ).where(base).group_by(TrafficLog.request_uri)
        .order_by(func.count(TrafficLog.id).desc()).limit(20)
    )).all()

    statuses = (await db.execute(
        select(TrafficLog.status, func.count(TrafficLog.id).label("count"))
        .where(base).group_by(TrafficLog.status)
        .order_by(func.count(TrafficLog.id).desc()).limit(15)
    )).all()

    # Grouped by ordinal, not by repeating the to_char() expression: asyncpg
    # binds the format string as a separate parameter each time it appears, so
    # Postgres does not see the SELECT and GROUP BY expressions as the same one
    # and rejects the query. Same approach as analytics_service.
    daily = (await db.execute(
        select(
            func.to_char(TrafficLog.timestamp, 'YYYY-MM-DD').label("date"),
            func.count(TrafficLog.id).label("requests"),
        ).where(base)
        .group_by(literal_column("1"))
        .order_by(literal_column("1"))
    )).all()

    recent = (await db.execute(
        select(TrafficLog).where(base)
        .order_by(TrafficLog.timestamp.desc()).limit(50)
    )).scalars().all()

    threats = (await db.execute(
        select(
            ThreatEvent.category,
            ThreatEvent.severity,
            func.count(ThreatEvent.id).label("count"),
            func.max(ThreatEvent.timestamp).label("last_seen"),
        ).where(and_(ThreatEvent.client_ip == ip, ThreatEvent.timestamp >= since))
        .group_by(ThreatEvent.category, ThreatEvent.severity)
        .order_by(func.count(ThreatEvent.id).desc())
    )).all()

    known = (await db.execute(select(KnownIp).where(KnownIp.ip_address == ip))).scalar_one_or_none()
    enrichment = (await db.execute(
        select(IpEnrichment).where(IpEnrichment.ip_address == ip)
    )).scalar_one_or_none()

    return {
        "ip_address": ip,
        "days": days,
        "known": (
            {"id": known.id, "label": known.label, "category": known.category,
             "notes": known.notes, "trusted": known.trusted}
            if known else None
        ),
        "enrichment": (
            {"country_code": enrichment.country_code, "country_name": enrichment.country_name,
             "city": enrichment.city, "isp": enrichment.isp, "org": enrichment.org,
             "asn": enrichment.asn, "as_name": enrichment.as_name,
             "reverse_dns": enrichment.reverse_dns}
            if enrichment else None
        ),
        "totals": {
            "requests": int(totals.requests or 0),
            "first_seen": totals.first_seen,
            "last_seen": totals.last_seen,
            "bytes_sent": int(totals.bytes_sent or 0),
            "bytes_received": int(totals.bytes_received or 0),
            "unique_paths": int(totals.unique_paths or 0),
            "hosts_touched": int(totals.hosts_touched or 0),
            "avg_response_time": int(totals.avg_response_time) if totals.avg_response_time else None,
            "errors": int(totals.errors or 0),
            "bot_requests": int(totals.bot_requests or 0),
        },
        "by_host": [
            {"host_id": r.proxy_host_id,
             "host_name": host_names.get(r.proxy_host_id, r.proxy_host_id or "unknown"),
             "requests": int(r.requests), "errors": int(r.errors or 0),
             "last_seen": r.last_seen}
            for r in per_host
        ],
        "top_paths": [
            {"uri": r.request_uri, "requests": int(r.requests), "last_status": r.last_status}
            for r in top_paths
        ],
        "status_breakdown": [
            {"status": r.status, "count": int(r.count)} for r in statuses
        ],
        "daily": [{"date": r.date, "requests": int(r.requests)} for r in daily],
        "threats": [
            {"category": r.category, "severity": r.severity,
             "count": int(r.count), "last_seen": r.last_seen}
            for r in threats
        ],
        "recent_requests": [
            {"timestamp": t.timestamp, "host_id": t.proxy_host_id,
             "host_name": host_names.get(t.proxy_host_id, "unknown"),
             "method": t.request_method, "uri": t.request_uri, "status": t.status,
             "response_time": t.response_time, "user_agent": t.user_agent}
            for t in recent
        ],
    }
