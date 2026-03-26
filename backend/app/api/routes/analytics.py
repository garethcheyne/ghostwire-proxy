from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, distinct, case, text
from datetime import datetime, timezone, timedelta
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.models.user import User
from app.models.traffic_log import TrafficLog
from app.models.proxy_host import ProxyHost
from app.api.deps import get_current_user

router = APIRouter()


class TimeSeriesPoint(BaseModel):
    timestamp: str
    requests: int
    unique_visitors: int
    bytes_sent: int
    bytes_received: int
    avg_response_time: float | None


class HostStats(BaseModel):
    host_id: str
    host_name: str
    requests: int
    unique_visitors: int
    bytes_sent: int
    avg_response_time: float | None
    error_rate: float


class StatusBreakdown(BaseModel):
    status_2xx: int
    status_3xx: int
    status_4xx: int
    status_5xx: int


class TopPage(BaseModel):
    uri: str
    requests: int
    avg_response_time: float | None


class TopReferrer(BaseModel):
    referer: str
    requests: int


class BrowserStats(BaseModel):
    browser: str
    requests: int
    percentage: float


class HourlyDistribution(BaseModel):
    hour: int
    requests: int


class AnalyticsDashboard(BaseModel):
    # Overview
    total_requests: int
    total_unique_visitors: int
    total_bytes_transferred: int
    avg_response_time: float | None
    error_rate: float

    # Comparisons
    requests_change_percent: float | None
    visitors_change_percent: float | None

    # Time series
    time_series: list[TimeSeriesPoint]

    # Breakdowns
    status_breakdown: StatusBreakdown
    requests_by_method: dict[str, int]

    # Top data
    top_hosts: list[HostStats]
    top_pages: list[TopPage]
    top_referrers: list[TopReferrer]
    top_ips: list[dict]

    # Distributions
    hourly_distribution: list[HourlyDistribution]
    browser_stats: list[BrowserStats]

    # Geographic (if available)
    country_stats: list[dict]

    # Error breakdown
    errors_by_host: list[dict]
    errors_by_status: list[dict]


def parse_user_agent(user_agent: str | None) -> str:
    """Extract browser name from user agent string."""
    if not user_agent:
        return "Unknown"

    ua_lower = user_agent.lower()

    if "edg" in ua_lower:
        return "Edge"
    elif "chrome" in ua_lower:
        return "Chrome"
    elif "firefox" in ua_lower:
        return "Firefox"
    elif "safari" in ua_lower:
        return "Safari"
    elif "opera" in ua_lower or "opr" in ua_lower:
        return "Opera"
    elif "msie" in ua_lower or "trident" in ua_lower:
        return "IE"
    elif "bot" in ua_lower or "crawl" in ua_lower or "spider" in ua_lower:
        return "Bot"
    elif "curl" in ua_lower:
        return "curl"
    elif "wget" in ua_lower:
        return "wget"
    elif "python" in ua_lower:
        return "Python"
    else:
        return "Other"


@router.get("/dashboard", response_model=AnalyticsDashboard)
async def get_analytics_dashboard(
    period: str = Query("7d", pattern="^(24h|7d|30d|90d)$"),
    proxy_host_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get comprehensive analytics dashboard data."""

    # Calculate time ranges
    now = datetime.now(timezone.utc)

    period_map = {
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
        "90d": timedelta(days=90),
    }

    period_delta = period_map[period]
    start_time = now - period_delta
    prev_start_time = start_time - period_delta

    # Base filter
    base_filter = [TrafficLog.timestamp >= start_time]
    prev_filter = [TrafficLog.timestamp >= prev_start_time, TrafficLog.timestamp < start_time]

    if proxy_host_id:
        base_filter.append(TrafficLog.proxy_host_id == proxy_host_id)
        prev_filter.append(TrafficLog.proxy_host_id == proxy_host_id)

    # === Current Period Stats ===

    # Total requests
    total_query = select(func.count(TrafficLog.id)).where(and_(*base_filter))
    total_requests = (await db.execute(total_query)).scalar() or 0

    # Unique visitors (by IP)
    unique_query = select(func.count(distinct(TrafficLog.client_ip))).where(and_(*base_filter))
    total_unique_visitors = (await db.execute(unique_query)).scalar() or 0

    # Total bytes
    bytes_query = select(
        func.coalesce(func.sum(TrafficLog.bytes_sent), 0),
        func.coalesce(func.sum(TrafficLog.bytes_received), 0)
    ).where(and_(*base_filter))
    bytes_result = (await db.execute(bytes_query)).first()
    total_bytes_sent = bytes_result[0] if bytes_result else 0
    total_bytes_received = bytes_result[1] if bytes_result else 0

    # Average response time
    avg_rt_query = select(func.avg(TrafficLog.response_time)).where(
        and_(*base_filter, TrafficLog.response_time.isnot(None))
    )
    avg_response_time = (await db.execute(avg_rt_query)).scalar()

    # Error rate (4xx + 5xx)
    error_query = select(func.count(TrafficLog.id)).where(
        and_(*base_filter, TrafficLog.status >= 400)
    )
    error_count = (await db.execute(error_query)).scalar() or 0
    error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0

    # === Previous Period Stats (for comparison) ===

    prev_requests_query = select(func.count(TrafficLog.id)).where(and_(*prev_filter))
    prev_requests = (await db.execute(prev_requests_query)).scalar() or 0

    prev_visitors_query = select(func.count(distinct(TrafficLog.client_ip))).where(and_(*prev_filter))
    prev_visitors = (await db.execute(prev_visitors_query)).scalar() or 0

    # Calculate change percentages
    requests_change = None
    if prev_requests > 0:
        requests_change = ((total_requests - prev_requests) / prev_requests) * 100

    visitors_change = None
    if prev_visitors > 0:
        visitors_change = ((total_unique_visitors - prev_visitors) / prev_visitors) * 100

    # === Time Series ===

    # Determine grouping interval based on period
    if period == "24h":
        interval_hours = 1
        time_format = "%Y-%m-%d %H:00"
    elif period == "7d":
        interval_hours = 6
        time_format = "%Y-%m-%d %H:00"
    elif period == "30d":
        interval_hours = 24
        time_format = "%Y-%m-%d"
    else:  # 90d
        interval_hours = 24 * 7
        time_format = "%Y-%m-%d"

    # Generate time buckets and aggregate
    time_series = []
    current_bucket = start_time

    while current_bucket < now:
        bucket_end = current_bucket + timedelta(hours=interval_hours)

        bucket_filter = base_filter.copy()
        bucket_filter[0] = TrafficLog.timestamp >= current_bucket
        bucket_filter.append(TrafficLog.timestamp < bucket_end)

        # Requests and unique visitors for this bucket
        bucket_stats = await db.execute(
            select(
                func.count(TrafficLog.id),
                func.count(distinct(TrafficLog.client_ip)),
                func.coalesce(func.sum(TrafficLog.bytes_sent), 0),
                func.coalesce(func.sum(TrafficLog.bytes_received), 0),
                func.avg(TrafficLog.response_time)
            ).where(and_(*bucket_filter))
        )
        stats = bucket_stats.first()

        time_series.append(TimeSeriesPoint(
            timestamp=current_bucket.strftime(time_format),
            requests=stats[0] or 0,
            unique_visitors=stats[1] or 0,
            bytes_sent=stats[2] or 0,
            bytes_received=stats[3] or 0,
            avg_response_time=round(float(stats[4]), 2) if stats[4] else None
        ))

        current_bucket = bucket_end

    # === Status Breakdown ===

    status_counts = {}
    for prefix in ['2', '3', '4', '5']:
        status_filter = base_filter.copy()
        status_filter.append(TrafficLog.status >= int(f"{prefix}00"))
        status_filter.append(TrafficLog.status < int(f"{prefix}00") + 100)

        count = (await db.execute(
            select(func.count(TrafficLog.id)).where(and_(*status_filter))
        )).scalar() or 0
        status_counts[f"status_{prefix}xx"] = count

    status_breakdown = StatusBreakdown(**status_counts)

    # === Requests by Method ===

    method_query = (
        select(TrafficLog.request_method, func.count(TrafficLog.id))
        .where(and_(*base_filter))
        .group_by(TrafficLog.request_method)
    )
    method_result = await db.execute(method_query)
    requests_by_method = {row[0]: row[1] for row in method_result.all()}

    # === Top Hosts ===

    top_hosts_query = (
        select(
            TrafficLog.proxy_host_id,
            func.count(TrafficLog.id).label('requests'),
            func.count(distinct(TrafficLog.client_ip)).label('unique_visitors'),
            func.coalesce(func.sum(TrafficLog.bytes_sent), 0).label('bytes_sent'),
            func.avg(TrafficLog.response_time).label('avg_rt'),
            func.sum(case((TrafficLog.status >= 400, 1), else_=0)).label('errors')
        )
        .where(and_(*base_filter))
        .group_by(TrafficLog.proxy_host_id)
        .order_by(func.count(TrafficLog.id).desc())
        .limit(10)
    )
    top_hosts_result = await db.execute(top_hosts_query)

    top_hosts = []
    for row in top_hosts_result.all():
        # Get host name
        host = (await db.execute(
            select(ProxyHost).where(ProxyHost.id == row[0])
        )).scalar_one_or_none()

        host_name = host.domain_names[0] if host and host.domain_names else "Unknown"
        host_error_rate = (row[5] / row[1] * 100) if row[1] > 0 else 0

        top_hosts.append(HostStats(
            host_id=row[0],
            host_name=host_name,
            requests=row[1],
            unique_visitors=row[2],
            bytes_sent=row[3],
            avg_response_time=round(float(row[4]), 2) if row[4] else None,
            error_rate=round(host_error_rate, 2)
        ))

    # === Top Pages ===

    top_pages_query = (
        select(
            TrafficLog.request_uri,
            func.count(TrafficLog.id).label('requests'),
            func.avg(TrafficLog.response_time).label('avg_rt')
        )
        .where(and_(*base_filter))
        .group_by(TrafficLog.request_uri)
        .order_by(func.count(TrafficLog.id).desc())
        .limit(10)
    )
    top_pages_result = await db.execute(top_pages_query)

    top_pages = [
        TopPage(
            uri=row[0][:100],  # Truncate long URIs
            requests=row[1],
            avg_response_time=round(float(row[2]), 2) if row[2] else None
        )
        for row in top_pages_result.all()
    ]

    # === Top Referrers ===

    top_referrers_query = (
        select(
            TrafficLog.referer,
            func.count(TrafficLog.id).label('requests')
        )
        .where(and_(*base_filter, TrafficLog.referer.isnot(None), TrafficLog.referer != ''))
        .group_by(TrafficLog.referer)
        .order_by(func.count(TrafficLog.id).desc())
        .limit(10)
    )
    top_referrers_result = await db.execute(top_referrers_query)

    top_referrers = [
        TopReferrer(referer=row[0][:100], requests=row[1])
        for row in top_referrers_result.all()
    ]

    # === Top IPs ===

    top_ips_query = (
        select(
            TrafficLog.client_ip,
            func.count(TrafficLog.id).label('requests'),
            func.max(TrafficLog.country_code).label('country_code'),
            func.max(TrafficLog.country_name).label('country_name'),
        )
        .where(and_(*base_filter))
        .group_by(TrafficLog.client_ip)
        .order_by(func.count(TrafficLog.id).desc())
        .limit(10)
    )
    top_ips_result = await db.execute(top_ips_query)
    top_ips = [{"ip": row[0], "requests": row[1], "country_code": row[2], "country_name": row[3]} for row in top_ips_result.all()]

    # === Hourly Distribution ===

    # Get all logs for the period and bucket by hour of day
    all_logs_query = (
        select(TrafficLog.timestamp)
        .where(and_(*base_filter))
    )
    all_logs = (await db.execute(all_logs_query)).scalars().all()

    hourly_counts = {h: 0 for h in range(24)}
    for ts in all_logs:
        hourly_counts[ts.hour] += 1

    hourly_distribution = [
        HourlyDistribution(hour=h, requests=c)
        for h, c in sorted(hourly_counts.items())
    ]

    # === Browser Stats ===

    ua_query = (
        select(TrafficLog.user_agent)
        .where(and_(*base_filter))
    )
    ua_result = (await db.execute(ua_query)).scalars().all()

    browser_counts: dict[str, int] = {}
    for ua in ua_result:
        browser = parse_user_agent(ua)
        browser_counts[browser] = browser_counts.get(browser, 0) + 1

    total_ua = sum(browser_counts.values())
    browser_stats = sorted([
        BrowserStats(
            browser=browser,
            requests=count,
            percentage=round(count / total_ua * 100, 1) if total_ua > 0 else 0
        )
        for browser, count in browser_counts.items()
    ], key=lambda x: x.requests, reverse=True)[:8]

    # === Country Stats ===

    country_query = (
        select(
            TrafficLog.country_code,
            func.count(TrafficLog.id).label('requests')
        )
        .where(and_(*base_filter, TrafficLog.country_code.isnot(None)))
        .group_by(TrafficLog.country_code)
        .order_by(func.count(TrafficLog.id).desc())
        .limit(10)
    )
    country_result = await db.execute(country_query)
    country_stats = [
        {"country": row[0], "requests": row[1]}
        for row in country_result.all()
    ]

    # === Errors by Host ===

    errors_by_host_query = (
        select(
            TrafficLog.proxy_host_id,
            TrafficLog.status,
            func.count(TrafficLog.id).label('count'),
        )
        .where(and_(*base_filter, TrafficLog.status >= 400))
        .group_by(TrafficLog.proxy_host_id, TrafficLog.status)
        .order_by(func.count(TrafficLog.id).desc())
        .limit(50)
    )
    errors_by_host_result = await db.execute(errors_by_host_query)

    errors_by_host_raw: dict[str, dict] = {}
    for row in errors_by_host_result.all():
        host_id = row[0]
        if host_id not in errors_by_host_raw:
            host = (await db.execute(
                select(ProxyHost).where(ProxyHost.id == host_id)
            )).scalar_one_or_none()
            errors_by_host_raw[host_id] = {
                "host_id": host_id,
                "host_name": host.domain_names[0] if host and host.domain_names else "Unknown",
                "total_errors": 0,
                "status_codes": {},
            }
        errors_by_host_raw[host_id]["total_errors"] += row[2]
        errors_by_host_raw[host_id]["status_codes"][str(row[1])] = row[2]

    errors_by_host = sorted(
        list(errors_by_host_raw.values()),
        key=lambda x: x["total_errors"],
        reverse=True,
    )[:10]

    # === Errors by Status Code ===

    errors_by_status_query = (
        select(
            TrafficLog.status,
            func.count(TrafficLog.id).label('count'),
        )
        .where(and_(*base_filter, TrafficLog.status >= 400))
        .group_by(TrafficLog.status)
        .order_by(func.count(TrafficLog.id).desc())
    )
    errors_by_status_result = await db.execute(errors_by_status_query)
    errors_by_status = [
        {"status": row[0], "count": row[1]}
        for row in errors_by_status_result.all()
    ]

    return AnalyticsDashboard(
        total_requests=total_requests,
        total_unique_visitors=total_unique_visitors,
        total_bytes_transferred=total_bytes_sent + total_bytes_received,
        avg_response_time=round(float(avg_response_time), 2) if avg_response_time else None,
        error_rate=round(error_rate, 2),
        requests_change_percent=round(requests_change, 1) if requests_change is not None else None,
        visitors_change_percent=round(visitors_change, 1) if visitors_change is not None else None,
        time_series=time_series,
        status_breakdown=status_breakdown,
        requests_by_method=requests_by_method,
        top_hosts=top_hosts,
        top_pages=top_pages,
        top_referrers=top_referrers,
        top_ips=top_ips,
        hourly_distribution=hourly_distribution,
        browser_stats=browser_stats,
        country_stats=country_stats,
        errors_by_host=errors_by_host,
        errors_by_status=errors_by_status,
    )


@router.get("/realtime")
async def get_realtime_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get real-time stats for the last 5 minutes."""

    now = datetime.now(timezone.utc)
    five_min_ago = now - timedelta(minutes=5)
    one_min_ago = now - timedelta(minutes=1)

    # Requests in last 5 minutes
    five_min_query = select(func.count(TrafficLog.id)).where(
        TrafficLog.timestamp >= five_min_ago
    )
    requests_5min = (await db.execute(five_min_query)).scalar() or 0

    # Requests in last minute
    one_min_query = select(func.count(TrafficLog.id)).where(
        TrafficLog.timestamp >= one_min_ago
    )
    requests_1min = (await db.execute(one_min_query)).scalar() or 0

    # Active visitors (unique IPs in last 5 min)
    active_query = select(func.count(distinct(TrafficLog.client_ip))).where(
        TrafficLog.timestamp >= five_min_ago
    )
    active_visitors = (await db.execute(active_query)).scalar() or 0

    # Recent errors
    error_query = select(func.count(TrafficLog.id)).where(
        and_(TrafficLog.timestamp >= five_min_ago, TrafficLog.status >= 400)
    )
    recent_errors = (await db.execute(error_query)).scalar() or 0

    return {
        "requests_per_minute": requests_1min,
        "requests_last_5min": requests_5min,
        "active_visitors": active_visitors,
        "recent_errors": recent_errors,
        "timestamp": now.isoformat(),
    }


@router.get("/auth-errors")
async def get_auth_errors(
    period: str = Query("24h", pattern="^(1h|24h|7d|30d|90d)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get 403/401 errors from traffic and failed login attempts from audit log."""
    from app.models.audit_log import AuditLog

    now = datetime.now(timezone.utc)
    period_map = {
        "1h": timedelta(hours=1),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
        "90d": timedelta(days=90),
    }
    start_time = now - period_map[period]

    # --- 403/401 from TrafficLog ---

    # Summary counts
    for_status = {}
    for code in [401, 403]:
        count = (await db.execute(
            select(func.count(TrafficLog.id)).where(
                and_(TrafficLog.timestamp >= start_time, TrafficLog.status == code)
            )
        )).scalar() or 0
        for_status[code] = count

    # Recent 403/401 events (last 50)
    recent_query = (
        select(
            TrafficLog.timestamp,
            TrafficLog.client_ip,
            TrafficLog.status,
            TrafficLog.request_method,
            TrafficLog.request_uri,
            TrafficLog.proxy_host_id,
            TrafficLog.user_agent,
            TrafficLog.country_code,
        )
        .where(and_(
            TrafficLog.timestamp >= start_time,
            TrafficLog.status.in_([401, 403]),
        ))
        .order_by(TrafficLog.timestamp.desc())
        .limit(50)
    )
    recent_result = await db.execute(recent_query)

    recent_events = []
    host_cache: dict[str, str] = {}
    for row in recent_result.all():
        host_id = row[5]
        if host_id and host_id not in host_cache:
            host = (await db.execute(
                select(ProxyHost).where(ProxyHost.id == host_id)
            )).scalar_one_or_none()
            host_cache[host_id] = host.domain_names[0] if host and host.domain_names else "Unknown"

        recent_events.append({
            "timestamp": row[0].isoformat(),
            "ip": row[1],
            "status": row[2],
            "method": row[3],
            "uri": (row[4] or "")[:100],
            "host": host_cache.get(host_id, "Unknown") if host_id else "Unknown",
            "country": row[7],
        })

    # Top IPs generating 403/401
    top_ips_query = (
        select(
            TrafficLog.client_ip,
            func.count(TrafficLog.id).label("count"),
            func.max(TrafficLog.timestamp).label("last_seen"),
        )
        .where(and_(
            TrafficLog.timestamp >= start_time,
            TrafficLog.status.in_([401, 403]),
        ))
        .group_by(TrafficLog.client_ip)
        .order_by(func.count(TrafficLog.id).desc())
        .limit(10)
    )
    top_ips_result = await db.execute(top_ips_query)
    top_offenders = [
        {"ip": row[0], "count": row[1], "last_seen": row[2].isoformat()}
        for row in top_ips_result.all()
    ]

    # Top hosts receiving 403/401
    top_hosts_query = (
        select(
            TrafficLog.proxy_host_id,
            func.count(TrafficLog.id).label("count"),
        )
        .where(and_(
            TrafficLog.timestamp >= start_time,
            TrafficLog.status.in_([401, 403]),
        ))
        .group_by(TrafficLog.proxy_host_id)
        .order_by(func.count(TrafficLog.id).desc())
        .limit(10)
    )
    top_hosts_result = await db.execute(top_hosts_query)
    top_hosts = []
    for row in top_hosts_result.all():
        hid = row[0]
        if hid and hid not in host_cache:
            host = (await db.execute(
                select(ProxyHost).where(ProxyHost.id == hid)
            )).scalar_one_or_none()
            host_cache[hid] = host.domain_names[0] if host and host.domain_names else "Unknown"
        top_hosts.append({
            "host": host_cache.get(hid, "Unknown") if hid else "Unknown",
            "count": row[1],
        })

    # --- Failed logins from AuditLog ---

    failed_logins_count = (await db.execute(
        select(func.count(AuditLog.id)).where(and_(
            AuditLog.timestamp >= start_time,
            AuditLog.action.in_(["login_failed", "auth_wall_login_failed"]),
        ))
    )).scalar() or 0

    recent_failed_logins_query = (
        select(
            AuditLog.timestamp,
            AuditLog.email,
            AuditLog.action,
            AuditLog.ip_address,
            AuditLog.details,
        )
        .where(and_(
            AuditLog.timestamp >= start_time,
            AuditLog.action.in_(["login_failed", "auth_wall_login_failed"]),
        ))
        .order_by(AuditLog.timestamp.desc())
        .limit(20)
    )
    recent_failed_result = await db.execute(recent_failed_logins_query)
    failed_logins = [
        {
            "timestamp": row[0].isoformat(),
            "email": row[1],
            "type": "admin" if row[2] == "login_failed" else "auth_wall",
            "ip": row[3],
            "details": row[4],
        }
        for row in recent_failed_result.all()
    ]

    return {
        "summary": {
            "total_401": for_status[401],
            "total_403": for_status[403],
            "failed_logins": failed_logins_count,
        },
        "recent_events": recent_events,
        "top_offenders": top_offenders,
        "top_hosts": top_hosts,
        "failed_logins": failed_logins,
    }
