from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, delete as sa_delete
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.core.database import get_db
from app.core.utils import get_client_ip
from app.models.user import User
from app.models.traffic_log import TrafficLog
from app.models.proxy_host import ProxyHost
from app.models.audit_log import AuditLog
from app.models.honeypot import IpEnrichment
from app.schemas.traffic import TrafficLogResponse, TrafficStatsResponse
from app.api.deps import get_current_user
from app.services.enrichment_service import backfill_enrichment

router = APIRouter()


@router.get("/", response_model=list[TrafficLogResponse])
async def list_traffic_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    proxy_host_id: Optional[str] = None,
    client_ip: Optional[str] = None,
    status_min: Optional[int] = None,
    status_max: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List traffic logs with filtering"""
    query = (
        select(TrafficLog, IpEnrichment.city)
        .outerjoin(IpEnrichment, TrafficLog.client_ip == IpEnrichment.ip_address)
        .options(selectinload(TrafficLog.proxy_host))
    )

    # Apply filters
    if proxy_host_id:
        query = query.where(TrafficLog.proxy_host_id == proxy_host_id)

    if client_ip:
        query = query.where(TrafficLog.client_ip == client_ip)

    if status_min is not None:
        query = query.where(TrafficLog.status >= status_min)

    if status_max is not None:
        query = query.where(TrafficLog.status <= status_max)

    if start_date:
        query = query.where(TrafficLog.timestamp >= start_date)

    if end_date:
        query = query.where(TrafficLog.timestamp <= end_date)

    query = query.order_by(TrafficLog.timestamp.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    # Build response with host_name and city from enrichment
    response = []
    for row in rows:
        log = row[0]
        city = row[1]
        log_dict = {
            "id": log.id,
            "proxy_host_id": log.proxy_host_id,
            "host_name": log.proxy_host.domain_names[0] if log.proxy_host and log.proxy_host.domain_names else None,
            "timestamp": log.timestamp,
            "client_ip": log.client_ip,
            "request_method": log.request_method,
            "request_uri": log.request_uri,
            "query_string": log.query_string,
            "status": log.status,
            "response_time": log.response_time,
            "bytes_sent": log.bytes_sent,
            "bytes_received": log.bytes_received,
            "upstream_addr": log.upstream_addr,
            "upstream_response_time": log.upstream_response_time,
            "ssl_protocol": log.ssl_protocol,
            "ssl_cipher": log.ssl_cipher,
            "user_agent": log.user_agent,
            "referer": log.referer,
            "country_code": log.country_code,
            "city": city,
            "auth_user": log.auth_user,
        }
        response.append(TrafficLogResponse(**log_dict))

    return response


@router.get("/stats", response_model=TrafficStatsResponse)
async def get_traffic_stats(
    proxy_host_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get traffic statistics"""
    # Base query
    base_filter = []
    if proxy_host_id:
        base_filter.append(TrafficLog.proxy_host_id == proxy_host_id)

    # Total requests
    total_query = select(func.count(TrafficLog.id))
    if base_filter:
        total_query = total_query.where(and_(*base_filter))
    total_requests = (await db.execute(total_query)).scalar() or 0

    # Requests today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_filter = base_filter + [TrafficLog.timestamp >= today_start]
    today_query = select(func.count(TrafficLog.id)).where(and_(*today_filter))
    requests_today = (await db.execute(today_query)).scalar() or 0

    # Requests this week
    week_start = today_start - timedelta(days=today_start.weekday())
    week_filter = base_filter + [TrafficLog.timestamp >= week_start]
    week_query = select(func.count(TrafficLog.id)).where(and_(*week_filter))
    requests_this_week = (await db.execute(week_query)).scalar() or 0

    # Requests by status (2xx, 3xx, 4xx, 5xx)
    requests_by_status = {}
    for status_prefix in ['2', '3', '4', '5']:
        status_filter = base_filter + [
            TrafficLog.status >= int(status_prefix + '00'),
            TrafficLog.status < int(status_prefix + '00') + 100
        ]
        status_query = select(func.count(TrafficLog.id)).where(and_(*status_filter))
        count = (await db.execute(status_query)).scalar() or 0
        requests_by_status[f"{status_prefix}xx"] = count

    # Requests by method
    method_query = (
        select(TrafficLog.request_method, func.count(TrafficLog.id))
        .group_by(TrafficLog.request_method)
    )
    if base_filter:
        method_query = method_query.where(and_(*base_filter))
    method_result = await db.execute(method_query)
    requests_by_method = {row[0]: row[1] for row in method_result.all()}

    # Average response time
    avg_query = select(func.avg(TrafficLog.response_time))
    if base_filter:
        avg_query = avg_query.where(and_(*base_filter))
    avg_response_time = (await db.execute(avg_query)).scalar()

    # Total bytes
    bytes_sent_query = select(func.sum(TrafficLog.bytes_sent))
    bytes_recv_query = select(func.sum(TrafficLog.bytes_received))
    if base_filter:
        bytes_sent_query = bytes_sent_query.where(and_(*base_filter))
        bytes_recv_query = bytes_recv_query.where(and_(*base_filter))
    total_bytes_sent = (await db.execute(bytes_sent_query)).scalar() or 0
    total_bytes_received = (await db.execute(bytes_recv_query)).scalar() or 0

    # Top IPs
    top_ips_query = (
        select(TrafficLog.client_ip, func.count(TrafficLog.id).label('count'))
        .group_by(TrafficLog.client_ip)
        .order_by(func.count(TrafficLog.id).desc())
        .limit(10)
    )
    if base_filter:
        top_ips_query = top_ips_query.where(and_(*base_filter))
    top_ips_result = await db.execute(top_ips_query)
    top_ips = [{"ip": row[0], "count": row[1]} for row in top_ips_result.all()]

    # Top hosts
    top_hosts_query = (
        select(TrafficLog.proxy_host_id, func.count(TrafficLog.id).label('count'))
        .group_by(TrafficLog.proxy_host_id)
        .order_by(func.count(TrafficLog.id).desc())
        .limit(10)
    )
    top_hosts_result = await db.execute(top_hosts_query)
    top_hosts_data = top_hosts_result.all()

    # Get host names
    top_hosts = []
    for host_id, count in top_hosts_data:
        host_result = await db.execute(select(ProxyHost).where(ProxyHost.id == host_id))
        host = host_result.scalar_one_or_none()
        host_name = host.domain_names[0] if host and host.domain_names else "Unknown"
        top_hosts.append({"host_id": host_id, "name": host_name, "count": count})

    return TrafficStatsResponse(
        total_requests=total_requests,
        requests_today=requests_today,
        requests_this_week=requests_this_week,
        requests_by_status=requests_by_status,
        requests_by_method=requests_by_method,
        avg_response_time=float(avg_response_time) if avg_response_time else None,
        total_bytes_sent=total_bytes_sent,
        total_bytes_received=total_bytes_received,
        top_ips=top_ips,
        top_hosts=top_hosts,
    )


@router.get("/geo/heatmap")
async def get_geo_heatmap(
    proxy_host_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get traffic count by country for heatmap visualization."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    query = (
        select(
            TrafficLog.country_code,
            TrafficLog.country_name,
            func.count(TrafficLog.id).label("count"),
        )
        .where(
            TrafficLog.country_code.isnot(None),
            TrafficLog.timestamp >= since,
        )
        .group_by(TrafficLog.country_code, TrafficLog.country_name)
        .order_by(func.count(TrafficLog.id).desc())
    )

    if proxy_host_id:
        query = query.where(TrafficLog.proxy_host_id == proxy_host_id)

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "country_code": row[0],
            "country_name": row[1] or row[0],
            "count": row[2],
        }
        for row in rows
    ]


@router.get("/geo/city-heatmap")
async def get_city_heatmap(
    proxy_host_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get traffic aggregated by city with lat/lon from IP enrichment data."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    base_filter = [
        TrafficLog.timestamp >= since,
        IpEnrichment.latitude.isnot(None),
        IpEnrichment.longitude.isnot(None),
    ]
    if proxy_host_id:
        base_filter.append(TrafficLog.proxy_host_id == proxy_host_id)

    query = (
        select(
            IpEnrichment.city,
            IpEnrichment.country_code,
            IpEnrichment.country_name,
            IpEnrichment.latitude,
            IpEnrichment.longitude,
            func.count(TrafficLog.id).label("count"),
            func.count(func.distinct(TrafficLog.client_ip)).label("unique_ips"),
        )
        .join(IpEnrichment, TrafficLog.client_ip == IpEnrichment.ip_address)
        .where(and_(*base_filter))
        .group_by(
            IpEnrichment.city,
            IpEnrichment.country_code,
            IpEnrichment.country_name,
            IpEnrichment.latitude,
            IpEnrichment.longitude,
        )
        .order_by(func.count(TrafficLog.id).desc())
        .limit(200)
    )

    result = await db.execute(query)
    return [
        {
            "city": row[0] or "Unknown",
            "country_code": row[1],
            "country_name": row[2],
            "lat": float(row[3]),
            "lon": float(row[4]),
            "count": row[5],
            "unique_ips": row[6],
        }
        for row in result.all()
    ]


@router.get("/enrichment/status")
async def get_enrichment_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of IP enrichment backfill — how many IPs still need enrichment."""
    subq = select(IpEnrichment.ip_address)
    total_unique = await db.execute(
        select(func.count(func.distinct(TrafficLog.client_ip)))
        .where(TrafficLog.client_ip.isnot(None))
    )
    enriched_count = await db.execute(
        select(func.count(func.distinct(TrafficLog.client_ip)))
        .where(
            TrafficLog.client_ip.isnot(None),
            TrafficLog.client_ip.in_(subq),
        )
    )
    total = total_unique.scalar() or 0
    enriched = enriched_count.scalar() or 0
    return {
        "total_unique_ips": total,
        "enriched": enriched,
        "remaining": total - enriched,
        "percent": round((enriched / total * 100) if total > 0 else 100, 1),
    }


@router.post("/enrichment/backfill")
async def trigger_enrichment_backfill(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger one batch of IP enrichment backfill."""
    result = await backfill_enrichment(db, batch_size=40)
    return result


@router.get("/{log_id}", response_model=TrafficLogResponse)
async def get_traffic_log(
    log_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get traffic log by ID"""
    result = await db.execute(select(TrafficLog).where(TrafficLog.id == log_id))
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Traffic log not found",
        )

    return log


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_traffic_log(
    log_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single traffic log entry."""
    result = await db.execute(select(TrafficLog).where(TrafficLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Traffic log not found")

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="traffic_log_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted traffic log {log_id}",
    ))
    await db.delete(log)
    await db.commit()


@router.delete("", status_code=status.HTTP_200_OK)
async def purge_traffic_logs(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Purge all traffic logs."""
    count_result = await db.execute(select(func.count(TrafficLog.id)))
    count = count_result.scalar() or 0

    await db.execute(sa_delete(TrafficLog))

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="traffic_logs_purged",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Purged all traffic logs ({count} records)",
    ))
    await db.commit()
    return {"status": "ok", "deleted": count}
