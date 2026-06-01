import asyncio
import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, distinct, case, text, cast, String
from datetime import datetime, timezone, timedelta
from typing import Optional
from pydantic import BaseModel

from app.core.database import get_db, AsyncSessionLocal
from app.core.cache import cached_json
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

    # Cache key based on period + optional host filter
    cache_key = f"analytics:dashboard:{period}:{proxy_host_id or 'all'}"

    async def _compute():
        return await _compute_dashboard(db, period, proxy_host_id)

    # Longer periods change slowly — scale TTL accordingly
    ttl_map = {"24h": 60, "7d": 120, "30d": 300, "90d": 600}
    result = await cached_json(cache_key, ttl=ttl_map.get(period, 60), producer=_compute)
    return result


async def _compute_dashboard(
    db: AsyncSession, period: str, proxy_host_id: Optional[str]
) -> AnalyticsDashboard:

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

    # === Phase 1: Overview + Prev period + Hosts (needed by later queries) ===

    overview_query = select(
        func.count(TrafficLog.id),
        func.count(distinct(TrafficLog.client_ip)),
        func.coalesce(func.sum(TrafficLog.bytes_sent), 0),
        func.coalesce(func.sum(TrafficLog.bytes_received), 0),
        func.avg(TrafficLog.response_time),
        func.sum(case((TrafficLog.status >= 400, 1), else_=0)),
        func.sum(case((and_(TrafficLog.status >= 200, TrafficLog.status < 300), 1), else_=0)),
        func.sum(case((and_(TrafficLog.status >= 300, TrafficLog.status < 400), 1), else_=0)),
        func.sum(case((and_(TrafficLog.status >= 400, TrafficLog.status < 500), 1), else_=0)),
        func.sum(case((TrafficLog.status >= 500, 1), else_=0)),
    ).where(and_(*base_filter))

    prev_query = select(
        func.count(TrafficLog.id),
        func.count(distinct(TrafficLog.client_ip)),
    ).where(and_(*prev_filter))

    # Run overview, prev_period, and host prefetch concurrently
    async def _run_overview():
        async with AsyncSessionLocal() as s:
            return (await s.execute(overview_query)).first()

    async def _run_prev():
        async with AsyncSessionLocal() as s:
            return (await s.execute(prev_query)).first()

    async def _run_hosts():
        async with AsyncSessionLocal() as s:
            result = await s.execute(select(ProxyHost))
            return {h.id: h for h in result.scalars().all()}

    ov, pv, host_map = await asyncio.gather(_run_overview(), _run_prev(), _run_hosts())

    total_requests = ov[0] or 0
    total_unique_visitors = ov[1] or 0
    total_bytes_sent = ov[2] or 0
    total_bytes_received = ov[3] or 0
    avg_response_time = ov[4]
    error_count = ov[5] or 0
    error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0

    status_breakdown = StatusBreakdown(
        status_2xx=ov[6] or 0,
        status_3xx=ov[7] or 0,
        status_4xx=ov[8] or 0,
        status_5xx=ov[9] or 0,
    )

    prev_requests = pv[0] or 0
    prev_visitors = pv[1] or 0

    requests_change = None
    if prev_requests > 0:
        requests_change = ((total_requests - prev_requests) / prev_requests) * 100

    visitors_change = None
    if prev_visitors > 0:
        visitors_change = ((total_unique_visitors - prev_visitors) / prev_visitors) * 100

    def get_host_name(host_id):
        h = host_map.get(host_id)
        return h.domain_names[0] if h and h.domain_names else "Unknown"

    # === Phase 2: Run all remaining queries concurrently ===

    # Time series
    if period == "24h":
        time_format = "%Y-%m-%d %H:00"
        trunc_expr = func.date_trunc('hour', TrafficLog.timestamp)
    elif period == "7d":
        time_format = "%Y-%m-%d %H:00"
        trunc_expr = func.to_timestamp(
            func.floor(func.extract('epoch', TrafficLog.timestamp) / 21600) * 21600
        )
    elif period == "30d":
        time_format = "%Y-%m-%d"
        trunc_expr = func.date_trunc('day', TrafficLog.timestamp)
    else:  # 90d
        time_format = "%Y-%m-%d"
        trunc_expr = func.date_trunc('week', TrafficLog.timestamp)

    ts_query = (
        select(
            trunc_expr.label('bucket'),
            func.count(TrafficLog.id),
            func.count(distinct(TrafficLog.client_ip)),
            func.coalesce(func.sum(TrafficLog.bytes_sent), 0),
            func.coalesce(func.sum(TrafficLog.bytes_received), 0),
            func.avg(TrafficLog.response_time),
        )
        .where(and_(*base_filter))
        .group_by(text('1'))
        .order_by(text('1'))
    )

    method_query = (
        select(TrafficLog.request_method, func.count(TrafficLog.id))
        .where(and_(*base_filter))
        .group_by(TrafficLog.request_method)
    )

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

    hourly_query = (
        select(
            func.extract('hour', TrafficLog.timestamp).label('hour'),
            func.count(TrafficLog.id).label('requests'),
        )
        .where(and_(*base_filter))
        .group_by(text('1'))
        .order_by(text('1'))
    )

    browser_case = case(
        (TrafficLog.user_agent.ilike('%edg%'), 'Edge'),
        (TrafficLog.user_agent.ilike('%chrome%'), 'Chrome'),
        (TrafficLog.user_agent.ilike('%firefox%'), 'Firefox'),
        (TrafficLog.user_agent.ilike('%safari%'), 'Safari'),
        (TrafficLog.user_agent.ilike('%opera%'), 'Opera'),
        (TrafficLog.user_agent.ilike('%opr%'), 'Opera'),
        (TrafficLog.user_agent.ilike('%bot%'), 'Bot'),
        (TrafficLog.user_agent.ilike('%crawl%'), 'Bot'),
        (TrafficLog.user_agent.ilike('%spider%'), 'Bot'),
        (TrafficLog.user_agent.ilike('%curl%'), 'curl'),
        (TrafficLog.user_agent.ilike('%python%'), 'Python'),
        (TrafficLog.user_agent.is_(None), 'Unknown'),
        else_='Other',
    ).label('browser')

    browser_query = (
        select(browser_case, func.count(TrafficLog.id).label('count'))
        .where(and_(*base_filter))
        .group_by(text('1'))
        .order_by(func.count(TrafficLog.id).desc())
        .limit(8)
    )

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

    errors_by_status_query = (
        select(
            TrafficLog.status,
            func.count(TrafficLog.id).label('count'),
        )
        .where(and_(*base_filter, TrafficLog.status >= 400))
        .group_by(TrafficLog.status)
        .order_by(func.count(TrafficLog.id).desc())
    )

    # Execute all 10 queries concurrently using separate sessions from the pool
    async def _exec(query):
        async with AsyncSessionLocal() as s:
            return (await s.execute(query)).all()

    (
        ts_rows, method_rows, hosts_rows, pages_rows,
        referrers_rows, ips_rows, hourly_rows, browser_rows,
        country_rows, err_host_rows, err_status_rows,
    ) = await asyncio.gather(
        _exec(ts_query),
        _exec(method_query),
        _exec(top_hosts_query),
        _exec(top_pages_query),
        _exec(top_referrers_query),
        _exec(top_ips_query),
        _exec(hourly_query),
        _exec(browser_query),
        _exec(country_query),
        _exec(errors_by_host_query),
        _exec(errors_by_status_query),
    )

    # === Format results ===

    # Time series
    time_series = []
    for row in ts_rows:
        bucket_ts = row[0]
        if bucket_ts is None:
            continue
        if isinstance(bucket_ts, (int, float)):
            bucket_ts = datetime.fromtimestamp(bucket_ts, tz=timezone.utc)
        time_series.append(TimeSeriesPoint(
            timestamp=bucket_ts.strftime(time_format),
            requests=row[1] or 0,
            unique_visitors=row[2] or 0,
            bytes_sent=row[3] or 0,
            bytes_received=row[4] or 0,
            avg_response_time=round(float(row[5]), 2) if row[5] else None,
        ))

    # Method breakdown
    requests_by_method = {row[0]: row[1] for row in method_rows}

    # Top hosts
    top_hosts = []
    for row in hosts_rows:
        host_error_rate = (row[5] / row[1] * 100) if row[1] > 0 else 0
        top_hosts.append(HostStats(
            host_id=row[0],
            host_name=get_host_name(row[0]),
            requests=row[1],
            unique_visitors=row[2],
            bytes_sent=row[3],
            avg_response_time=round(float(row[4]), 2) if row[4] else None,
            error_rate=round(host_error_rate, 2)
        ))

    # Top pages
    top_pages = [
        TopPage(
            uri=row[0][:100],
            requests=row[1],
            avg_response_time=round(float(row[2]), 2) if row[2] else None
        )
        for row in pages_rows
    ]

    # Top referrers
    top_referrers = [
        TopReferrer(referer=row[0][:100], requests=row[1])
        for row in referrers_rows
    ]

    # Top IPs
    top_ips = [{"ip": row[0], "requests": row[1], "country_code": row[2], "country_name": row[3]} for row in ips_rows]

    # Hourly distribution
    hourly_counts = {h: 0 for h in range(24)}
    for row in hourly_rows:
        hourly_counts[int(row[0])] = row[1]
    hourly_distribution = [
        HourlyDistribution(hour=h, requests=c)
        for h, c in sorted(hourly_counts.items())
    ]

    # Browser stats
    total_ua = total_requests or 1
    browser_stats = [
        BrowserStats(
            browser=row[0],
            requests=row[1],
            percentage=round(row[1] / total_ua * 100, 1)
        )
        for row in browser_rows
    ]

    # Country stats
    country_stats = [
        {"country": row[0], "requests": row[1]}
        for row in country_rows
    ]

    # Errors by host
    errors_by_host_raw: dict[str, dict] = {}
    for row in err_host_rows:
        host_id = row[0]
        if host_id not in errors_by_host_raw:
            errors_by_host_raw[host_id] = {
                "host_id": host_id,
                "host_name": get_host_name(host_id),
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

    # Errors by status
    errors_by_status = [
        {"status": row[0], "count": row[1]}
        for row in err_status_rows
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
):
    """Get real-time stats for the last 5 minutes."""

    async def _compute():
        now = datetime.now(timezone.utc)
        five_min_ago = now - timedelta(minutes=5)
        one_min_ago = now - timedelta(minutes=1)

        async def _q(query):
            async with AsyncSessionLocal() as s:
                return (await s.execute(query)).scalar() or 0

        requests_5min, requests_1min, active_visitors, recent_errors = await asyncio.gather(
            _q(select(func.count(TrafficLog.id)).where(TrafficLog.timestamp >= five_min_ago)),
            _q(select(func.count(TrafficLog.id)).where(TrafficLog.timestamp >= one_min_ago)),
            _q(select(func.count(distinct(TrafficLog.client_ip))).where(TrafficLog.timestamp >= five_min_ago)),
            _q(select(func.count(TrafficLog.id)).where(and_(TrafficLog.timestamp >= five_min_ago, TrafficLog.status >= 400))),
        )

        return {
            "requests_per_minute": requests_1min,
            "requests_last_5min": requests_5min,
            "active_visitors": active_visitors,
            "recent_errors": recent_errors,
            "timestamp": now.isoformat(),
        }

    return await cached_json("analytics:realtime", ttl=10, producer=_compute)


@router.get("/auth-errors")
async def get_auth_errors(
    period: str = Query("24h", pattern="^(1h|24h|7d|30d|90d)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get 403/401 errors from traffic and failed login attempts from audit log.

    Cached for 30s — dashboard reload should not trigger a full recompute.
    """
    from app.models.audit_log import AuditLog

    cache_key = f"analytics:auth_errors:{period}"

    async def _compute() -> dict:
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

        # Single query: counts for 401 + 403 in one round trip.
        summary_row = (await db.execute(
            select(
                func.count(case((TrafficLog.status == 401, 1))).label("c401"),
                func.count(case((TrafficLog.status == 403, 1))).label("c403"),
            ).where(TrafficLog.timestamp >= start_time)
        )).one()
        for_status = {401: summary_row.c401 or 0, 403: summary_row.c403 or 0}

        # Recent events — JOIN ProxyHost so we don't N+1 to resolve names.
        recent_query = (
            select(
                TrafficLog.timestamp,
                TrafficLog.client_ip,
                TrafficLog.status,
                TrafficLog.request_method,
                TrafficLog.request_uri,
                TrafficLog.proxy_host_id,
                TrafficLog.country_code,
                ProxyHost.domain_names,
            )
            .join(ProxyHost, ProxyHost.id == TrafficLog.proxy_host_id, isouter=True)
            .where(and_(
                TrafficLog.timestamp >= start_time,
                TrafficLog.status.in_([401, 403]),
            ))
            .order_by(TrafficLog.timestamp.desc())
            .limit(50)
        )
        recent_result = await db.execute(recent_query)
        recent_events = [
            {
                "timestamp": row[0].isoformat(),
                "ip": row[1],
                "status": row[2],
                "method": row[3],
                "uri": (row[4] or "")[:100],
                "host": (row[7][0] if row[7] else "Unknown"),
                "country": row[6],
            }
            for row in recent_result.all()
        ]

        # Top IPs generating 403/401
        top_ips_result = await db.execute(
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
        top_offenders = [
            {"ip": row[0], "count": row[1], "last_seen": row[2].isoformat()}
            for row in top_ips_result.all()
        ]

        # Top hosts receiving 403/401 — JOIN to resolve host name in one query.
        top_hosts_result = await db.execute(
            select(
                TrafficLog.proxy_host_id,
                func.max(cast(ProxyHost.domain_names, String)).label("domain_names"),
                func.count(TrafficLog.id).label("count"),
            )
            .join(ProxyHost, ProxyHost.id == TrafficLog.proxy_host_id, isouter=True)
            .where(and_(
                TrafficLog.timestamp >= start_time,
                TrafficLog.status.in_([401, 403]),
            ))
            .group_by(TrafficLog.proxy_host_id)
            .order_by(func.count(TrafficLog.id).desc())
            .limit(10)
        )
        top_hosts = []
        for row in top_hosts_result.all():
            try:
                names = json.loads(row[1]) if row[1] else []
            except (TypeError, ValueError):
                names = []
            top_hosts.append({
                "host": (names[0] if names else "Unknown"),
                "count": row[2],
            })

        # --- Failed logins from AuditLog ---
        failed_logins_count = (await db.execute(
            select(func.count(AuditLog.id)).where(and_(
                AuditLog.timestamp >= start_time,
                AuditLog.action.in_(["login_failed", "auth_wall_login_failed"]),
            ))
        )).scalar() or 0

        recent_failed_result = await db.execute(
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

    return await cached_json(cache_key, ttl=30, producer=_compute)
