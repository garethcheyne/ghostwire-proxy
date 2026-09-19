"""Full per-host traffic report.

The analytics dashboard answers "how is the fleet doing". This answers "what
happened on *this* site" — the report you would hand to whoever owns the domain:
what they serve, who asked for it, from where, on what, and who attacked it.

Two data sources, deliberately:

- `traffic_logs` for anything needing request detail (paths, user agents,
  referrers). Retention prunes these, so this half only ever covers the
  retention window.
- `analytics_daily` / `analytics_geo` rollups for lifetime and long-range
  figures, which survive pruning. That is why "lifetime requests" can be far
  larger than anything the log-derived sections can see.

Both are labelled as such in the response so the UI never implies the detail
sections cover the lifetime span.
"""
import asyncio
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, and_, distinct, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.analytics import AnalyticsDaily, AnalyticsGeo
from app.models.proxy_host import ProxyHost
from app.models.traffic_log import TrafficLog
from app.models.waf import ThreatEvent
from app.services.client_classifier import parse_browser, parse_os, parse_device_type, classify_bot

logger = logging.getLogger(__name__)

PERIODS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "365d": timedelta(days=365),
}

# How many rows each "top N" section returns. Enough to be useful in a report,
# small enough that the payload stays sane.
TOP_N = 25

# Sampling ceiling for the user-agent sections. Browser/OS/device have to be
# derived in Python (the UA string is unparseable in SQL), so a host with
# millions of rows would otherwise stream the lot. We take the most recent
# SAMPLE_LIMIT rows and report the sample size alongside, rather than quietly
# presenting a partial count as a total.
SAMPLE_LIMIT = 50_000


def _percent(part: int, whole: int) -> float:
    return round(part / whole * 100, 2) if whole else 0.0


def _f(value, places: int = 1) -> Optional[float]:
    """Coerce a SQL aggregate to a plain rounded float.

    Postgres returns Decimal for avg()/percentile_cont(). Decimal is not JSON
    serialisable, and this report is cached as JSON — so leaving one in the
    payload fails the whole request, not just that field.
    """
    if value is None:
        return None
    try:
        return round(float(value), places)
    except (TypeError, ValueError):
        return None


def _i(value) -> int:
    """Coerce a SQL aggregate to a plain int."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


async def build_host_report(
    db: AsyncSession,
    host: ProxyHost,
    period: str = "30d",
) -> dict:
    """Assemble the full report for one host."""
    now = datetime.now(timezone.utc)
    delta = PERIODS.get(period, PERIODS["30d"])
    start = now - delta
    prev_start = start - delta

    host_filter = TrafficLog.proxy_host_id == host.id
    window = and_(host_filter, TrafficLog.timestamp >= start)
    prev_window = and_(
        host_filter, TrafficLog.timestamp >= prev_start, TrafficLog.timestamp < start
    )

    # Each block opens its own session so they can genuinely run concurrently —
    # a single AsyncSession serialises its queries.
    results = await asyncio.gather(
        _overview(window, prev_window),
        _timeseries(host.id, start, period),
        _top_paths(window),
        _status_and_methods(window),
        _client_breakdown(window),
        _geography(window),
        _referrers(window),
        _visitors(window),
        _security(host.id, start, prev_start),
        _lifetime(host.id),
        return_exceptions=True,
    )

    names = [
        "overview", "timeseries", "paths", "responses", "clients",
        "geography", "referrers", "visitors", "security", "lifetime",
    ]
    report: dict = {}
    for name, value in zip(names, results):
        if isinstance(value, Exception):
            # One failing section shouldn't blank the whole report.
            logger.error("Host report section %r failed for %s: %s", name, host.id, value)
            report[name] = {"error": str(value)}
        else:
            report[name] = value

    report["host"] = {
        "id": host.id,
        "domain_names": host.domain_names or [],
        "primary_domain": (host.domain_names or ["(unnamed)"])[0],
        "forward_host": getattr(host, "forward_host", None),
        "forward_port": getattr(host, "forward_port", None),
        "enabled": getattr(host, "enabled", None),
    }
    report["meta"] = {
        "period": period,
        "period_start": start.isoformat(),
        "period_end": now.isoformat(),
        "generated_at": now.isoformat(),
        "detail_source": "traffic_logs (subject to retention)",
        "lifetime_source": "analytics_daily rollups",
    }
    return report


async def _overview(window, prev_window) -> dict:
    """Headline numbers, and how they moved against the preceding period."""
    async with AsyncSessionLocal() as s:
        # is_streaming rows are excluded from latency only — a websocket that
        # stayed open 40 minutes is not a 40-minute response time.
        latency_filter = and_(window, TrafficLog.is_streaming.isnot(True))

        row = (await s.execute(
            select(
                func.count(TrafficLog.id),
                func.count(distinct(TrafficLog.client_ip)),
                func.coalesce(func.sum(TrafficLog.bytes_sent), 0),
                func.coalesce(func.sum(TrafficLog.bytes_received), 0),
                func.sum(case((TrafficLog.status >= 400, 1), else_=0)),
                func.sum(case((TrafficLog.is_bot.is_(True), 1), else_=0)),
                func.count(distinct(TrafficLog.auth_user)),
            ).where(window)
        )).first()

        latency = (await s.execute(
            select(
                func.avg(TrafficLog.response_time),
                func.percentile_cont(0.5).within_group(TrafficLog.response_time.asc()),
                func.percentile_cont(0.95).within_group(TrafficLog.response_time.asc()),
                func.percentile_cont(0.99).within_group(TrafficLog.response_time.asc()),
                func.max(TrafficLog.response_time),
            ).where(and_(latency_filter, TrafficLog.response_time.isnot(None)))
        )).first()

        prev = (await s.execute(
            select(
                func.count(TrafficLog.id),
                func.count(distinct(TrafficLog.client_ip)),
            ).where(prev_window)
        )).first()

    requests = row[0] or 0
    visitors = row[1] or 0
    errors = row[4] or 0
    bots = row[5] or 0
    prev_requests = prev[0] or 0
    prev_visitors = prev[1] or 0

    def change(current: int, previous: int) -> Optional[float]:
        if not previous:
            return None
        return round((current - previous) / previous * 100, 1)

    return {
        "total_requests": requests,
        "unique_visitors": visitors,
        "bytes_sent": _i(row[2]),
        "bytes_received": _i(row[3]),
        "error_count": errors,
        "error_rate": _percent(errors, requests),
        "bot_requests": bots,
        "bot_percent": _percent(bots, requests),
        "human_requests": requests - bots,
        "identified_users": row[6] or 0,
        "avg_response_time_ms": _f(latency[0]),
        "p50_response_time_ms": _f(latency[1]),
        "p95_response_time_ms": _f(latency[2]),
        "p99_response_time_ms": _f(latency[3]),
        "max_response_time_ms": _i(latency[4]) if latency[4] is not None else None,
        "requests_change_percent": change(requests, prev_requests),
        "visitors_change_percent": change(visitors, prev_visitors),
        "previous_requests": prev_requests,
        "previous_visitors": prev_visitors,
    }


async def _timeseries(host_id: str, start: datetime, period: str) -> dict:
    """Requests over time. Hourly for a day, daily beyond that."""
    bucket = "hour" if period == "24h" else "day"

    async with AsyncSessionLocal() as s:
        trunc = func.date_trunc(bucket, TrafficLog.timestamp)
        rows = (await s.execute(
            select(
                trunc.label("bucket"),
                func.count(TrafficLog.id),
                func.count(distinct(TrafficLog.client_ip)),
                func.coalesce(func.sum(TrafficLog.bytes_sent), 0),
                func.sum(case((TrafficLog.status >= 400, 1), else_=0)),
                func.sum(case((TrafficLog.is_bot.is_(True), 1), else_=0)),
                func.avg(TrafficLog.response_time),
            )
            .where(and_(TrafficLog.proxy_host_id == host_id, TrafficLog.timestamp >= start))
            .group_by("bucket")
            .order_by("bucket")
        )).all()

    return {
        "bucket": bucket,
        "points": [
            {
                "timestamp": r[0].isoformat() if r[0] else None,
                "requests": r[1] or 0,
                "unique_visitors": r[2] or 0,
                "bytes_sent": _i(r[3]),
                "errors": r[4] or 0,
                "bot_requests": r[5] or 0,
                "avg_response_time_ms": _f(r[6]),
            }
            for r in rows
        ],
    }


async def _top_paths(window) -> dict:
    """Which URLs this site actually serves, and which of them hurt."""
    async with AsyncSessionLocal() as s:
        popular = (await s.execute(
            select(
                TrafficLog.request_uri,
                func.count(TrafficLog.id).label("requests"),
                func.count(distinct(TrafficLog.client_ip)),
                func.avg(TrafficLog.response_time),
                func.coalesce(func.sum(TrafficLog.bytes_sent), 0),
                func.sum(case((TrafficLog.status >= 400, 1), else_=0)),
            )
            .where(window)
            .group_by(TrafficLog.request_uri)
            .order_by(func.count(TrafficLog.id).desc())
            .limit(TOP_N)
        )).all()

        # Slowest paths, by p95 rather than mean, and only where there is enough
        # volume for a percentile to mean anything.
        slowest = (await s.execute(
            select(
                TrafficLog.request_uri,
                func.count(TrafficLog.id).label("requests"),
                func.percentile_cont(0.95).within_group(TrafficLog.response_time.asc()),
                func.avg(TrafficLog.response_time),
            )
            .where(and_(
                window,
                TrafficLog.response_time.isnot(None),
                TrafficLog.is_streaming.isnot(True),
            ))
            .group_by(TrafficLog.request_uri)
            .having(func.count(TrafficLog.id) >= 10)
            .order_by(func.percentile_cont(0.95).within_group(TrafficLog.response_time.asc()).desc())
            .limit(TOP_N)
        )).all()

        erroring = (await s.execute(
            select(
                TrafficLog.request_uri,
                func.count(TrafficLog.id).label("errors"),
                func.max(TrafficLog.status),
            )
            .where(and_(window, TrafficLog.status >= 400))
            .group_by(TrafficLog.request_uri)
            .order_by(func.count(TrafficLog.id).desc())
            .limit(TOP_N)
        )).all()

    return {
        "top_paths": [
            {
                "uri": r[0],
                "requests": r[1],
                "unique_visitors": r[2],
                "avg_response_time_ms": _f(r[3]),
                "bytes_sent": _i(r[4]),
                "errors": r[5] or 0,
                "error_rate": _percent(r[5] or 0, r[1]),
            }
            for r in popular
        ],
        "slowest_paths": [
            {
                "uri": r[0],
                "requests": r[1],
                "p95_response_time_ms": _f(r[2]),
                "avg_response_time_ms": _f(r[3]),
            }
            for r in slowest
        ],
        "error_paths": [
            {"uri": r[0], "errors": r[1], "example_status": r[2]}
            for r in erroring
        ],
    }


async def _status_and_methods(window) -> dict:
    async with AsyncSessionLocal() as s:
        statuses = (await s.execute(
            select(TrafficLog.status, func.count(TrafficLog.id))
            .where(window)
            .group_by(TrafficLog.status)
            .order_by(func.count(TrafficLog.id).desc())
        )).all()

        methods = (await s.execute(
            select(TrafficLog.request_method, func.count(TrafficLog.id))
            .where(window)
            .group_by(TrafficLog.request_method)
            .order_by(func.count(TrafficLog.id).desc())
        )).all()

    total = sum(c for _, c in statuses) or 0
    families = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "other": 0}
    for code, count in statuses:
        if code is None:
            families["other"] += count
        elif 200 <= code < 300:
            families["2xx"] += count
        elif 300 <= code < 400:
            families["3xx"] += count
        elif 400 <= code < 500:
            families["4xx"] += count
        elif code >= 500:
            families["5xx"] += count
        else:
            families["other"] += count

    return {
        "status_families": families,
        "status_codes": [
            {"status": c, "requests": n, "percent": _percent(n, total)}
            for c, n in statuses[:TOP_N]
        ],
        "methods": [
            {"method": m or "UNKNOWN", "requests": n, "percent": _percent(n, total)}
            for m, n in methods
        ],
    }


async def _client_breakdown(window) -> dict:
    """Browser, OS, device and bot mix.

    User-Agent strings can't be grouped in SQL, so this samples the most recent
    rows and reports how many it looked at.
    """
    async with AsyncSessionLocal() as s:
        total = (await s.execute(
            select(func.count(TrafficLog.id)).where(window)
        )).scalar() or 0

        rows = (await s.execute(
            select(TrafficLog.user_agent, TrafficLog.is_bot)
            .where(window)
            .order_by(TrafficLog.timestamp.desc())
            .limit(SAMPLE_LIMIT)
        )).all()

    browsers: Counter = Counter()
    systems: Counter = Counter()
    devices: Counter = Counter()
    bot_names: Counter = Counter()
    humans = 0
    bots = 0

    for ua, is_bot in rows:
        browsers[parse_browser(ua)] += 1
        systems[parse_os(ua)] += 1
        devices[parse_device_type(ua)] += 1

        # Trust the stored classification where it exists; fall back to parsing
        # for rows written before is_bot was introduced.
        flagged = is_bot if is_bot is not None else classify_bot(ua)[0]
        if flagged:
            bots += 1
            _, name = classify_bot(ua)
            bot_names[name or "Unnamed automation"] += 1
        else:
            humans += 1

    sample = len(rows)

    def top(counter: Counter) -> list[dict]:
        return [
            {"name": name, "requests": n, "percent": _percent(n, sample)}
            for name, n in counter.most_common(TOP_N)
        ]

    return {
        "sample_size": sample,
        "total_in_period": total,
        "sampled": sample < total,
        "browsers": top(browsers),
        "operating_systems": top(systems),
        "devices": top(devices),
        "bots": top(bot_names),
        "human_requests": humans,
        "bot_requests": bots,
        "human_percent": _percent(humans, sample),
        "bot_percent": _percent(bots, sample),
    }


async def _geography(window) -> dict:
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(
                TrafficLog.country_code,
                func.max(TrafficLog.country_name),
                func.count(TrafficLog.id),
                func.count(distinct(TrafficLog.client_ip)),
                func.coalesce(func.sum(TrafficLog.bytes_sent), 0),
            )
            .where(and_(window, TrafficLog.country_code.isnot(None)))
            .group_by(TrafficLog.country_code)
            .order_by(func.count(TrafficLog.id).desc())
            .limit(TOP_N)
        )).all()

        unknown = (await s.execute(
            select(func.count(TrafficLog.id))
            .where(and_(window, TrafficLog.country_code.is_(None)))
        )).scalar() or 0

    total = sum(r[2] for r in rows) + unknown

    return {
        "countries": [
            {
                "country_code": r[0],
                "country_name": r[1] or r[0],
                "requests": r[2],
                "unique_visitors": r[3],
                "bytes_sent": _i(r[4]),
                "percent": _percent(r[2], total),
            }
            for r in rows
        ],
        "unlocated_requests": unknown,
    }


async def _referrers(window) -> dict:
    """Where visitors arrived from. Direct traffic sends no Referer at all."""
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(TrafficLog.referer, func.count(TrafficLog.id))
            .where(and_(window, TrafficLog.referer.isnot(None), TrafficLog.referer != ""))
            .group_by(TrafficLog.referer)
            .order_by(func.count(TrafficLog.id).desc())
            .limit(TOP_N)
        )).all()

        direct = (await s.execute(
            select(func.count(TrafficLog.id))
            .where(and_(window, (TrafficLog.referer.is_(None)) | (TrafficLog.referer == "")))
        )).scalar() or 0

    # Group by originating domain as well as exact URL — "which site sends me
    # traffic" is usually the more useful question.
    domains: Counter = Counter()
    for ref, count in rows:
        try:
            domain = ref.split("//", 1)[-1].split("/", 1)[0].lower()
        except Exception:
            domain = ref
        domains[domain] += count

    return {
        "referrers": [{"referer": r[0], "requests": r[1]} for r in rows],
        "referring_domains": [
            {"domain": d, "requests": n} for d, n in domains.most_common(TOP_N)
        ],
        "direct_requests": direct,
    }


async def _visitors(window) -> dict:
    async with AsyncSessionLocal() as s:
        top_ips = (await s.execute(
            select(
                TrafficLog.client_ip,
                func.count(TrafficLog.id),
                func.max(TrafficLog.country_name),
                func.coalesce(func.sum(TrafficLog.bytes_sent), 0),
                func.max(TrafficLog.timestamp),
                func.sum(case((TrafficLog.is_bot.is_(True), 1), else_=0)),
            )
            .where(window)
            .group_by(TrafficLog.client_ip)
            .order_by(func.count(TrafficLog.id).desc())
            .limit(TOP_N)
        )).all()

        users = (await s.execute(
            select(
                TrafficLog.auth_user,
                func.count(TrafficLog.id),
                func.count(distinct(TrafficLog.client_ip)),
                func.max(TrafficLog.timestamp),
            )
            .where(and_(window, TrafficLog.auth_user.isnot(None)))
            .group_by(TrafficLog.auth_user)
            .order_by(func.count(TrafficLog.id).desc())
            .limit(TOP_N)
        )).all()

    return {
        "top_ips": [
            {
                "client_ip": r[0],
                "requests": r[1],
                "country_name": r[2],
                "bytes_sent": _i(r[3]),
                "last_seen": r[4].isoformat() if r[4] else None,
                "bot_requests": r[5] or 0,
            }
            for r in top_ips
        ],
        "authenticated_users": [
            {
                "username": r[0],
                "requests": r[1],
                "distinct_ips": r[2],
                "last_seen": r[3].isoformat() if r[3] else None,
            }
            for r in users
        ],
    }


async def _security(host_id: str, start: datetime, prev_start: datetime) -> dict:
    """What attacked this host, how, and whether it got through."""
    scoped = and_(ThreatEvent.proxy_host_id == host_id, ThreatEvent.timestamp >= start)

    async with AsyncSessionLocal() as s:
        totals = (await s.execute(
            select(
                func.count(ThreatEvent.id),
                func.count(distinct(ThreatEvent.client_ip)),
                func.sum(case((ThreatEvent.action_taken == "blocked", 1), else_=0)),
                func.sum(case((ThreatEvent.action_taken == "blocklisted", 1), else_=0)),
                func.sum(case((ThreatEvent.action_taken == "logged", 1), else_=0)),
            ).where(scoped)
        )).first()

        previous = (await s.execute(
            select(func.count(ThreatEvent.id)).where(and_(
                ThreatEvent.proxy_host_id == host_id,
                ThreatEvent.timestamp >= prev_start,
                ThreatEvent.timestamp < start,
            ))
        )).scalar() or 0

        categories = (await s.execute(
            select(ThreatEvent.category, func.count(ThreatEvent.id))
            .where(scoped).group_by(ThreatEvent.category)
            .order_by(func.count(ThreatEvent.id).desc()).limit(TOP_N)
        )).all()

        severities = (await s.execute(
            select(ThreatEvent.severity, func.count(ThreatEvent.id))
            .where(scoped).group_by(ThreatEvent.severity)
            .order_by(func.count(ThreatEvent.id).desc())
        )).all()

        attackers = (await s.execute(
            select(
                ThreatEvent.client_ip,
                func.count(ThreatEvent.id),
                func.max(ThreatEvent.timestamp),
                func.max(ThreatEvent.category),
                func.sum(case((ThreatEvent.action_taken.in_(("blocked", "blocklisted")), 1), else_=0)),
            )
            .where(scoped).group_by(ThreatEvent.client_ip)
            .order_by(func.count(ThreatEvent.id).desc()).limit(TOP_N)
        )).all()

        targets = (await s.execute(
            select(ThreatEvent.request_uri, func.count(ThreatEvent.id))
            .where(scoped).group_by(ThreatEvent.request_uri)
            .order_by(func.count(ThreatEvent.id).desc()).limit(TOP_N)
        )).all()

        rules = (await s.execute(
            select(ThreatEvent.rule_name, func.count(ThreatEvent.id))
            .where(and_(scoped, ThreatEvent.rule_name.isnot(None)))
            .group_by(ThreatEvent.rule_name)
            .order_by(func.count(ThreatEvent.id).desc()).limit(TOP_N)
        )).all()

        daily = (await s.execute(
            select(
                func.date_trunc("day", ThreatEvent.timestamp).label("bucket"),
                func.count(ThreatEvent.id),
            )
            .where(scoped).group_by("bucket").order_by("bucket")
        )).all()

    total_events = totals[0] or 0
    blocked = (totals[2] or 0) + (totals[3] or 0)

    return {
        "total_events": total_events,
        "unique_attackers": totals[1] or 0,
        "blocked": totals[2] or 0,
        "blocklisted": totals[3] or 0,
        "logged_only": totals[4] or 0,
        "blocked_percent": _percent(blocked, total_events),
        "previous_period_events": previous,
        "events_change_percent": (
            round((total_events - previous) / previous * 100, 1) if previous else None
        ),
        "by_category": [{"category": c or "uncategorised", "events": n} for c, n in categories],
        "by_severity": [{"severity": sv or "unknown", "events": n} for sv, n in severities],
        "top_attackers": [
            {
                "client_ip": r[0],
                "events": r[1],
                "last_seen": r[2].isoformat() if r[2] else None,
                "category": r[3],
                "blocked": r[4] or 0,
            }
            for r in attackers
        ],
        "targeted_paths": [{"uri": r[0], "events": r[1]} for r in targets],
        "triggered_rules": [{"rule_name": r[0], "events": r[1]} for r in rules],
        "daily": [
            {"date": r[0].strftime("%Y-%m-%d") if r[0] else None, "events": r[1]}
            for r in daily
        ],
    }


async def _lifetime(host_id: str) -> dict:
    """Totals since the host was created, from rollups rather than raw logs.

    These survive retention pruning, so this is the only honest source for
    "total traffic ever" — which is exactly what a site owner asks for.
    """
    async with AsyncSessionLocal() as s:
        row = (await s.execute(
            select(
                func.coalesce(func.sum(AnalyticsDaily.total_requests), 0),
                func.coalesce(func.sum(AnalyticsDaily.blocked_requests), 0),
                func.coalesce(func.sum(AnalyticsDaily.total_threats), 0),
                func.coalesce(func.sum(AnalyticsDaily.bytes_sent), 0),
                func.coalesce(func.sum(AnalyticsDaily.bytes_received), 0),
                func.coalesce(func.sum(AnalyticsDaily.bot_requests), 0),
                func.min(AnalyticsDaily.date),
                func.max(AnalyticsDaily.date),
                func.count(AnalyticsDaily.id),
                func.max(AnalyticsDaily.unique_ips),
            ).where(AnalyticsDaily.proxy_host_id == host_id)
        )).first()

        busiest = (await s.execute(
            select(AnalyticsDaily.date, AnalyticsDaily.total_requests)
            .where(AnalyticsDaily.proxy_host_id == host_id)
            .order_by(AnalyticsDaily.total_requests.desc())
            .limit(1)
        )).first()

        countries = (await s.execute(
            select(
                AnalyticsGeo.country_code,
                func.coalesce(func.sum(AnalyticsGeo.requests), 0),
                func.coalesce(func.sum(AnalyticsGeo.threats), 0),
            )
            .where(AnalyticsGeo.proxy_host_id == host_id)
            .group_by(AnalyticsGeo.country_code)
            .order_by(func.sum(AnalyticsGeo.requests).desc())
            .limit(TOP_N)
        )).all()

    days = row[8] or 0
    total = _i(row[0])

    return {
        "total_requests": total,
        "blocked_requests": _i(row[1]),
        "total_threats": _i(row[2]),
        "bytes_sent": _i(row[3]),
        "bytes_received": _i(row[4]),
        "bot_requests": _i(row[5]),
        "first_date": row[6],
        "last_date": row[7],
        "days_with_traffic": days,
        "avg_requests_per_day": round(total / days, 1) if days else 0.0,
        # Peak single-day unique IPs, not a lifetime distinct count: the rollups
        # store a daily figure, and summing those would count a returning
        # visitor once per day.
        "peak_daily_unique_ips": _i(row[9]),
        "busiest_day": (
            {"date": busiest[0], "requests": busiest[1]} if busiest else None
        ),
        "top_countries": [
            {"country_code": c, "requests": _i(n), "threats": _i(t)}
            for c, n, t in countries
        ],
    }
