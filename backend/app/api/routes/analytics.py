import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import String, and_, case, cast, distinct, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.cache import cached_json
from app.core.database import AsyncSessionLocal, get_db
from app.models.analytics import AnalyticsDaily, AnalyticsGeo
from app.models.proxy_host import ProxyHost
from app.models.traffic_log import TrafficLog
from app.models.user import User
from app.services import traffic_query as tq

logger = logging.getLogger(__name__)

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
    proxy_host_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get comprehensive analytics dashboard data."""

    # Cache key based on period + optional host filter
    cache_key = f"analytics:dashboard:{period}:{proxy_host_id or 'all'}"

    async def _compute():
        return await _compute_dashboard(db, period, proxy_host_id)

    # Longer periods change slowly — scale TTL accordingly
    ttl_map = {"24h": 60, "7d": 300, "30d": 900, "90d": 1800}
    result = await cached_json(cache_key, ttl=ttl_map.get(period, 60), producer=_compute)
    return result


# The dashboard used to fire 13 aggregates over raw traffic_logs at once, each with
# parallel workers: a 30-day view read the whole table 13 times concurrently and
# pinned Postgres. Now everything the hourly rollup keeps (counts, status, bytes,
# latency, hosts, methods, time series) comes from it via traffic_query, and the
# fields it drops (visitors, pages, referrers, IPs, browsers, countries) from two
# raw scans. At most two raw scans run at once across all dashboard requests.
_RAW_SCANS = asyncio.Semaphore(2)
# Long windows read up to the whole retention period of raw rows.
_RAW_TIMEOUT_MS = {"24h": 30_000, "7d": 60_000, "30d": 120_000, "90d": 120_000}

_PERIODS = {
    # period: (window, chart bucket, chart label format)
    "24h": (timedelta(hours=24), timedelta(hours=1), "%Y-%m-%d %H:00"),
    "7d": (timedelta(days=7), timedelta(hours=6), "%Y-%m-%d %H:00"),
    "30d": (timedelta(days=30), timedelta(days=1), "%Y-%m-%d"),
    # Weekly buckets start on Monday (tq.ORIGIN is a Monday), like date_trunc('week').
    "90d": (timedelta(days=90), timedelta(days=7), "%Y-%m-%d"),
}

_BROWSER_SQL = """CASE
    WHEN user_agent IS NULL THEN 'Unknown'
    WHEN user_agent ILIKE '%edg%' THEN 'Edge'
    WHEN user_agent ILIKE '%chrome%' THEN 'Chrome'
    WHEN user_agent ILIKE '%firefox%' THEN 'Firefox'
    WHEN user_agent ILIKE '%safari%' THEN 'Safari'
    WHEN user_agent ILIKE '%opera%' OR user_agent ILIKE '%opr%' THEN 'Opera'
    WHEN user_agent ILIKE '%bot%' OR user_agent ILIKE '%crawl%' OR user_agent ILIKE '%spider%' THEN 'Bot'
    WHEN user_agent ILIKE '%curl%' THEN 'curl'
    WHEN user_agent ILIKE '%python%' THEN 'Python'
    ELSE 'Other' END"""

# Distinct visitors overall (this period and the previous one), per chart bucket
# and per host, in one pass. Deduplicating first keeps the DISTINCT counts small.
_VISITORS_SQL = """
SELECT CASE WHEN GROUPING(bucket) = 0 THEN 'bucket' WHEN GROUPING(host) = 0 THEN 'host' ELSE 'total' END AS kind,
       cur, bucket, host, count(DISTINCT client_ip) AS visitors
FROM (
    SELECT DISTINCT
        timestamp >= :start AS cur,
        CASE WHEN timestamp >= :start
             THEN date_bin(CAST(:stride AS interval), timestamp, CAST(:origin AS timestamptz)) END AS bucket,
        CASE WHEN timestamp >= :start THEN proxy_host_id END AS host,
        client_ip
    FROM traffic_logs
    WHERE timestamp >= :prev_start {host_filter}
) d
GROUP BY GROUPING SETS ((cur), (bucket), (host))
"""

# Top 10 of each raw-only dimension in one pass.
_KIND_SQL = (
    "CASE WHEN GROUPING(request_uri) = 0 THEN 'page' WHEN GROUPING(referer) = 0 THEN 'referer' "
    "WHEN GROUPING(client_ip) = 0 THEN 'ip' WHEN GROUPING(country_code) = 0 THEN 'country' ELSE 'browser' END"
)
_VALUE_SQL = "CAST(COALESCE(request_uri, referer, client_ip, country_code, browser) AS text)"
_TOP_SQL = f"""
SELECT kind, value, requests, avg_rt, ip_cc, ip_cn FROM (
    SELECT {_KIND_SQL} AS kind,
           {_VALUE_SQL} AS value,
           count(*) AS requests,
           avg(response_time) AS avg_rt,
           max(ip_cc) AS ip_cc,
           max(ip_cn) AS ip_cn,
           row_number() OVER (
               PARTITION BY {_KIND_SQL}
               ORDER BY {_VALUE_SQL} IS NULL, count(*) DESC
           ) AS rn
    FROM (
        SELECT CAST(request_uri AS text) AS request_uri,
               CAST(NULLIF(referer, '') AS text) AS referer,
               CAST(client_ip AS text) AS client_ip,
               CAST(country_code AS text) AS country_code,
               {_BROWSER_SQL} AS browser,
               response_time,
               country_code AS ip_cc,
               country_name AS ip_cn
        FROM traffic_logs
        WHERE timestamp >= :start {{host_filter}}
    ) r
    GROUP BY GROUPING SETS ((request_uri), (referer), (client_ip), (country_code), (browser))
) x
WHERE rn <= 10 AND value IS NOT NULL
"""  # noqa: S608  only fixed SQL is interpolated; values are bound parameters


async def _raw_scan(sql: str, params: dict, timeout_ms: int) -> list | None:
    """Rows of a raw-table scan, or None if it ran out of time.

    The rollup-backed half of the dashboard is still worth showing then, so a slow
    scan blanks only the lists it feeds instead of failing the whole page.
    """
    async with _RAW_SCANS, AsyncSessionLocal() as s:
        await s.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
        try:
            return (await s.execute(text(sql), params)).mappings().all()
        except DBAPIError as e:
            if "statement timeout" not in str(e):
                raise
            logger.warning("Analytics dashboard: raw scan timed out after %d ms", timeout_ms)
            return None


def _avg_rt(m: dict) -> float | None:
    return round(m["rt_sum"] / m["rt_count"], 2) if m["rt_count"] else None


async def _compute_dashboard(db: AsyncSession, period: str, proxy_host_id: str | None) -> AnalyticsDashboard:
    now = datetime.now(UTC)
    window, stride, time_format = _PERIODS[period]
    # On a whole hour, so the rollup covers the whole window but the newest
    # (not yet summarised) hour; a partial first hour is read from raw rows, and
    # one busy hour there (an attack, a scan) made every rollup query slow.
    start_time = tq.floor_hour(now - window)
    prev_start_time = start_time - window
    host_ids = [proxy_host_id] if proxy_host_id else []
    f = tq.TrafficFilters(start=start_time, host_ids=host_ids)
    prev_f = tq.TrafficFilters(start=prev_start_time, end=start_time, host_ids=host_ids)

    host_filter = "AND proxy_host_id = :host" if proxy_host_id else ""
    # Retention keeps only so much raw traffic. When the previous period starts
    # before the oldest row there is nothing to compare against, and scanning
    # back to it would read the whole table for no result.
    async with AsyncSessionLocal() as s:
        oldest = (await s.execute(select(func.min(TrafficLog.timestamp)))).scalar()
    compare = oldest is not None and oldest <= prev_start_time
    raw_params: dict = {
        "start": start_time,
        "prev_start": prev_start_time if compare else start_time,
        "stride": stride,
        "origin": tq.ORIGIN,
    }
    raw_timeout = _RAW_TIMEOUT_MS[period]
    if proxy_host_id:
        raw_params["host"] = proxy_host_id

    async def _q(fn):
        async with AsyncSessionLocal() as s:
            return await fn(s)

    async def _hosts(s):
        return {h.id: h for h in (await s.execute(select(ProxyHost))).scalars().all()}

    hourly_stride = timedelta(hours=1)
    (
        host_status_rows,
        prev_rows,
        ts_rows,
        hour_rows,
        method_rows,
        host_map,
        visitor_rows,
        top_rows,
    ) = await asyncio.gather(
        _q(lambda s: tq.aggregate(s, f, ["proxy_host_id", "status"])),
        _q(lambda s: tq.aggregate(s, prev_f)),
        _q(lambda s: tq.aggregate(s, f, stride=stride, order="bucket")),
        _q(lambda s: tq.aggregate(s, f, stride=hourly_stride, order="bucket"))
        if stride != hourly_stride
        else asyncio.sleep(0, result=None),
        _q(lambda s: tq.method_counts(s, f, limit=50)),
        _q(_hosts),
        _raw_scan(_VISITORS_SQL.format(host_filter=host_filter), raw_params, raw_timeout),
        _raw_scan(_TOP_SQL.format(host_filter=host_filter), raw_params, raw_timeout),
    )
    if hour_rows is None:
        hour_rows = ts_rows

    def get_host_name(host_id):
        h = host_map.get(host_id)
        return h.domain_names[0] if h and h.domain_names else "Unknown"

    # === Overview, status, hosts and errors, from one (host, status) aggregate ===
    overall = tq.merge(host_status_rows)
    total_requests = overall["requests"]
    by_class = {c: 0 for c in range(1, 6)}
    per_host: dict[str | None, list[dict]] = {}
    errors_by_status_map: dict[int, int] = {}
    errors_by_host_raw: dict[str | None, dict] = {}
    for r in host_status_rows:
        status = int(r["status"] or 0)
        by_class[min(max(status // 100, 1), 5)] += r["requests"]
        per_host.setdefault(r["proxy_host_id"], []).append(r)
        if status >= 400:
            errors_by_status_map[status] = errors_by_status_map.get(status, 0) + r["requests"]
            e = errors_by_host_raw.setdefault(
                r["proxy_host_id"],
                {
                    "host_id": r["proxy_host_id"],
                    "host_name": get_host_name(r["proxy_host_id"]),
                    "total_errors": 0,
                    "status_codes": {},
                },
            )
            e["total_errors"] += r["requests"]
            e["status_codes"][str(status)] = e["status_codes"].get(str(status), 0) + r["requests"]

    error_count = by_class[4] + by_class[5]
    error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0
    status_breakdown = StatusBreakdown(
        status_2xx=by_class[2],
        status_3xx=by_class[3],
        status_4xx=by_class[4],
        status_5xx=by_class[5],
    )

    # === Visitors ===
    total_unique_visitors = 0
    prev_visitors = 0
    bucket_visitors: dict[datetime, int] = {}
    host_visitors: dict[str, int] = {}
    for r in visitor_rows or []:
        if r["kind"] == "total":
            if r["cur"]:
                total_unique_visitors = int(r["visitors"])
            elif r["cur"] is not None:
                prev_visitors = int(r["visitors"])
        elif r["kind"] == "bucket" and r["bucket"] is not None:
            bucket_visitors[r["bucket"]] = int(r["visitors"])
        elif r["kind"] == "host" and r["host"] is not None:
            host_visitors[r["host"]] = int(r["visitors"])

    prev_requests = tq.merge(prev_rows)["requests"] if compare else 0
    requests_change = ((total_requests - prev_requests) / prev_requests * 100) if prev_requests > 0 else None
    visitors_change = (
        ((total_unique_visitors - prev_visitors) / prev_visitors * 100) if prev_visitors > 0 else None
    )

    # === Time series ===
    time_series = [
        TimeSeriesPoint(
            timestamp=r["bucket"].astimezone(UTC).strftime(time_format),
            requests=r["requests"],
            unique_visitors=bucket_visitors.get(r["bucket"], 0),
            bytes_sent=r["bytes_sent"],
            bytes_received=r["bytes_received"],
            avg_response_time=_avg_rt(r),
        )
        for r in ts_rows
        if r["bucket"] is not None
    ]

    hourly_counts = {h: 0 for h in range(24)}
    for r in hour_rows:
        if r["bucket"] is not None:
            hourly_counts[r["bucket"].astimezone(UTC).hour] += r["requests"]
    hourly_distribution = [HourlyDistribution(hour=h, requests=c) for h, c in sorted(hourly_counts.items())]

    requests_by_method = {r["value"]: r["requests"] for r in method_rows if r["value"]}

    # === Top hosts ===
    host_totals = sorted(
        ((hid, tq.merge(rows)) for hid, rows in per_host.items()),
        key=lambda kv: kv[1]["requests"],
        reverse=True,
    )[:10]
    top_hosts = []
    for hid, m in host_totals:
        host_errors = sum(r["requests"] for r in per_host[hid] if (r["status"] or 0) >= 400)
        top_hosts.append(
            HostStats(
                host_id=hid or "",
                host_name=get_host_name(hid),
                requests=m["requests"],
                unique_visitors=host_visitors.get(hid, 0) if hid else 0,
                bytes_sent=m["bytes_sent"],
                avg_response_time=_avg_rt(m),
                error_rate=round((host_errors / m["requests"] * 100) if m["requests"] else 0, 2),
            )
        )

    # === Raw-only top lists ===
    tops: dict[str, list] = {"page": [], "referer": [], "ip": [], "country": [], "browser": []}
    for r in top_rows or []:
        tops[r["kind"]].append(r)
    for rows in tops.values():
        rows.sort(key=lambda r: r["requests"], reverse=True)

    top_pages = [
        TopPage(
            uri=r["value"][:100],
            requests=r["requests"],
            avg_response_time=round(float(r["avg_rt"]), 2) if r["avg_rt"] else None,
        )
        for r in tops["page"]
    ]
    top_referrers = [TopReferrer(referer=r["value"][:100], requests=r["requests"]) for r in tops["referer"]]
    top_ips = [
        {"ip": r["value"], "requests": r["requests"], "country_code": r["ip_cc"], "country_name": r["ip_cn"]}
        for r in tops["ip"]
    ]
    total_ua = total_requests or 1
    browser_stats = [
        BrowserStats(browser=r["value"], requests=r["requests"], percentage=round(r["requests"] / total_ua * 100, 1))
        for r in tops["browser"][:8]
    ]
    country_stats = [{"country": r["value"], "requests": r["requests"]} for r in tops["country"]]

    errors_by_host = sorted(errors_by_host_raw.values(), key=lambda x: x["total_errors"], reverse=True)[:10]
    errors_by_status = [
        {"status": s, "count": c} for s, c in sorted(errors_by_status_map.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return AnalyticsDashboard(
        total_requests=total_requests,
        total_unique_visitors=total_unique_visitors,
        total_bytes_transferred=overall["bytes_sent"] + overall["bytes_received"],
        avg_response_time=_avg_rt(overall),
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
        now = datetime.now(UTC)
        five_min_ago = now - timedelta(minutes=5)
        one_min_ago = now - timedelta(minutes=1)

        async def _q(query):
            async with AsyncSessionLocal() as s:
                return (await s.execute(query)).scalar() or 0

        requests_5min, requests_1min, active_visitors, recent_errors = await asyncio.gather(
            _q(select(func.count(TrafficLog.id)).where(TrafficLog.timestamp >= five_min_ago)),
            _q(select(func.count(TrafficLog.id)).where(TrafficLog.timestamp >= one_min_ago)),
            _q(select(func.count(distinct(TrafficLog.client_ip))).where(TrafficLog.timestamp >= five_min_ago)),
            _q(
                select(func.count(TrafficLog.id)).where(
                    and_(TrafficLog.timestamp >= five_min_ago, TrafficLog.status >= 400)
                )
            ),
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
        now = datetime.now(UTC)
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
        summary_row = (
            await db.execute(
                select(
                    func.count(case((TrafficLog.status == 401, 1))).label("c401"),
                    func.count(case((TrafficLog.status == 403, 1))).label("c403"),
                ).where(TrafficLog.timestamp >= start_time)
            )
        ).one()
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
            .where(
                and_(
                    TrafficLog.timestamp >= start_time,
                    TrafficLog.status.in_([401, 403]),
                )
            )
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
            .where(
                and_(
                    TrafficLog.timestamp >= start_time,
                    TrafficLog.status.in_([401, 403]),
                )
            )
            .group_by(TrafficLog.client_ip)
            .order_by(func.count(TrafficLog.id).desc())
            .limit(10)
        )
        top_offenders = [
            {"ip": row[0], "count": row[1], "last_seen": row[2].isoformat()} for row in top_ips_result.all()
        ]

        # Top hosts receiving 403/401 — JOIN to resolve host name in one query.
        top_hosts_result = await db.execute(
            select(
                TrafficLog.proxy_host_id,
                func.max(cast(ProxyHost.domain_names, String)).label("domain_names"),
                func.count(TrafficLog.id).label("count"),
            )
            .join(ProxyHost, ProxyHost.id == TrafficLog.proxy_host_id, isouter=True)
            .where(
                and_(
                    TrafficLog.timestamp >= start_time,
                    TrafficLog.status.in_([401, 403]),
                )
            )
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
            top_hosts.append(
                {
                    "host": (names[0] if names else "Unknown"),
                    "count": row[2],
                }
            )

        # --- Failed logins from AuditLog ---
        failed_logins_count = (
            await db.execute(
                select(func.count(AuditLog.id)).where(
                    and_(
                        AuditLog.timestamp >= start_time,
                        AuditLog.action.in_(["login_failed", "auth_wall_login_failed"]),
                    )
                )
            )
        ).scalar() or 0

        recent_failed_result = await db.execute(
            select(
                AuditLog.timestamp,
                AuditLog.email,
                AuditLog.action,
                AuditLog.ip_address,
                AuditLog.details,
            )
            .where(
                and_(
                    AuditLog.timestamp >= start_time,
                    AuditLog.action.in_(["login_failed", "auth_wall_login_failed"]),
                )
            )
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


# ─── Long-range trends ────────────────────────────────────────────────────────
# These read the analytics_* rollups rather than traffic_logs, which is the only
# way to answer questions that reach further back than the retention window —
# raw rows are pruned nightly, the summaries are not.


class TrendPoint(BaseModel):
    date: str
    requests: int
    unique_visitors: int
    blocked: int
    threats: int
    bytes_sent: int
    bytes_received: int
    avg_response_time: int | None = None
    p95_response_time: int | None = None
    p99_response_time: int | None = None
    bot_requests: int = 0


class HostTrendSeries(BaseModel):
    host_id: str
    host_name: str
    points: list[TrendPoint]


class TrendsResponse(BaseModel):
    days: int
    totals: list[TrendPoint]
    by_host: list[HostTrendSeries]
    top_countries: list[dict]


@router.get("/trends", response_model=TrendsResponse)
async def get_trends(
    days: int = Query(90, ge=1, le=730),
    proxy_host_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Daily trends from the analytics rollups (cached 5 minutes).

    Deliberately not computed from traffic_logs: retention prunes those, so a
    live query can never look further back than the retention window.
    """
    cache_key = f"analytics:trends:{proxy_host_id or 'all'}:{days}"

    async def _compute() -> dict:
        since = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")

        rows_q = select(AnalyticsDaily).where(AnalyticsDaily.date >= since)
        if proxy_host_id:
            rows_q = rows_q.where(AnalyticsDaily.proxy_host_id == proxy_host_id)
        rows = (await db.execute(rows_q.order_by(AnalyticsDaily.date))).scalars().all()

        host_names: dict[str, str] = {}
        for host in (await db.execute(select(ProxyHost))).scalars().all():
            host_names[host.id] = (host.domain_names or [host.id])[0]

        # Fleet totals per day. unique_ips can't be summed across hosts without
        # double-counting a visitor who hit two sites, so it is reported as the
        # largest single-host figure for the day — an honest lower bound rather
        # than an inflated total.
        totals: dict[str, dict] = {}
        per_host: dict[str, list] = {}

        for r in rows:
            t = totals.setdefault(
                r.date,
                {
                    "date": r.date,
                    "requests": 0,
                    "unique_visitors": 0,
                    "blocked": 0,
                    "threats": 0,
                    "bytes_sent": 0,
                    "bytes_received": 0,
                    "bot_requests": 0,
                    "p95_response_time": None,
                    "p99_response_time": None,
                    "_rt_weighted": 0,
                    "_rt_requests": 0,
                },
            )
            t["requests"] += r.total_requests or 0
            t["blocked"] += r.blocked_requests or 0
            t["threats"] += r.total_threats or 0
            t["bytes_sent"] += r.bytes_sent or 0
            t["bytes_received"] += r.bytes_received or 0
            t["unique_visitors"] = max(t["unique_visitors"], r.unique_ips or 0)
            t["bot_requests"] += r.bot_requests or 0
            # Percentiles can't be averaged across hosts, so the fleet figure is
            # the worst host that day — which is the one you'd want to act on.
            for key, value in (
                ("p95_response_time", r.p95_response_time_ms),
                ("p99_response_time", r.p99_response_time_ms),
            ):
                if value is not None:
                    t[key] = value if t[key] is None else max(t[key], value)
            if r.avg_response_time_ms and r.total_requests:
                t["_rt_weighted"] += r.avg_response_time_ms * r.total_requests
                t["_rt_requests"] += r.total_requests

            per_host.setdefault(r.proxy_host_id or "unknown", []).append(
                {
                    "date": r.date,
                    "requests": r.total_requests or 0,
                    "unique_visitors": r.unique_ips or 0,
                    "blocked": r.blocked_requests or 0,
                    "threats": r.total_threats or 0,
                    "bytes_sent": r.bytes_sent or 0,
                    "bytes_received": r.bytes_received or 0,
                    "avg_response_time": r.avg_response_time_ms,
                    "p95_response_time": r.p95_response_time_ms,
                    "p99_response_time": r.p99_response_time_ms,
                    "bot_requests": r.bot_requests or 0,
                }
            )

        totals_list = []
        for date in sorted(totals):
            t = totals[date]
            rt_w = t.pop("_rt_weighted")
            rt_n = t.pop("_rt_requests")
            # Request-weighted, so a quiet host with one slow request doesn't
            # drag the fleet average around.
            t["avg_response_time"] = int(rt_w / rt_n) if rt_n else None
            totals_list.append(t)

        by_host = [
            {
                "host_id": hid,
                "host_name": host_names.get(hid, hid),
                "points": sorted(points, key=lambda p: p["date"]),
            }
            for hid, points in sorted(
                per_host.items(),
                key=lambda kv: sum(p["requests"] for p in kv[1]),
                reverse=True,
            )[:10]
        ]

        geo_q = select(
            AnalyticsGeo.country_code,
            func.sum(AnalyticsGeo.requests).label("requests"),
            func.sum(AnalyticsGeo.blocked).label("blocked"),
        ).where(AnalyticsGeo.date >= since)
        if proxy_host_id:
            geo_q = geo_q.where(AnalyticsGeo.proxy_host_id == proxy_host_id)
        geo_rows = (
            await db.execute(
                geo_q.group_by(AnalyticsGeo.country_code).order_by(func.sum(AnalyticsGeo.requests).desc()).limit(15)
            )
        ).all()

        return {
            "days": days,
            "totals": totals_list,
            "by_host": by_host,
            "top_countries": [
                {"country": g.country_code, "requests": int(g.requests or 0), "blocked": int(g.blocked or 0)}
                for g in geo_rows
            ],
        }

    return await cached_json(cache_key, ttl=300, producer=_compute)
