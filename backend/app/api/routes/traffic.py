"""Traffic logs: the request list, summaries and per-backend / host / client drill-downs.

Everything takes the same filter parameters (see ``traffic_filters``) and is answered
by app.services.traffic_query, which reads the hourly rollup where it can and raw
traffic_logs otherwise. Lists are paginated and every aggregate is bounded (time
window, LIMIT, statement timeout).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import and_, delete as sa_delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user, get_current_user
from app.core.cache import cached_json
from app.core.database import get_db
from app.core.utils import get_client_ip
from app.models.audit_log import AuditLog
from app.models.honeypot import IpEnrichment
from app.models.known_ip import KnownIp
from app.models.traffic_log import TrafficLog
from app.models.user import User
from app.models.waf import ThreatActor, ThreatEvent
from app.schemas.traffic import TrafficLogResponse, TrafficStatsResponse
from app.services import traffic_query as tq
from app.services import traffic_nodes as tn
from app.services import traffic_rollup_service
from app.services.enrichment_service import backfill_enrichment

router = APIRouter()

# Short: the figures are near-live; this only absorbs refetch bursts (several
# panels asking within seconds) and repeated identical views.
VIEW_CACHE_TTL = 20


def traffic_filters(default_range: Optional[str]) -> Callable[..., tq.TrafficFilters]:
    """FastAPI dependency building TrafficFilters from query parameters.

    ``default_range`` applies when neither ``range`` nor start/end is given: the
    log list keeps its old "everything" default (None); summaries use 24h.
    """

    def dep(
        range: Optional[str] = Query(None, description="15m, 1h, 6h, 24h, 7d, 30d, 90d or all"),
        start: Optional[datetime] = Query(None),
        end: Optional[datetime] = Query(None),
        start_date: Optional[datetime] = Query(None, description="Legacy alias of start"),
        end_date: Optional[datetime] = Query(None, description="Legacy alias of end"),
        host: list[str] = Query([], description="Proxy host id (repeatable)"),
        proxy_host_id: Optional[str] = Query(None, description="Legacy single host"),
        backend: list[str] = Query([], description="Upstream 'ip:port', or 'ip' for every port"),
        status_class: list[int] = Query([], description="1-5 (repeatable)"),
        status_code: list[int] = Query([], alias="status", description="Exact status code (repeatable)"),
        status_min: Optional[int] = Query(None),
        status_max: Optional[int] = Query(None),
        method: list[str] = Query([]),
        path: Optional[str] = Query(None, max_length=500),
        path_mode: str = Query("contains", pattern="^(contains|prefix)$"),
        client_ip: Optional[str] = Query(None, max_length=64, description="Address or CIDR"),
        country: list[str] = Query([]),
        ua: Optional[str] = Query(None, max_length=200, description="User agent contains"),
        bot: Optional[bool] = Query(None),
        min_rt: Optional[int] = Query(None, ge=0, description="Slower than (ms)"),
        search: Optional[str] = Query(None, max_length=200),
    ) -> tq.TrafficFilters:
        try:
            s, e = tq.resolve_range(range, start or start_date, end or end_date, default=default_range)
            hosts = list(host) + ([proxy_host_id] if proxy_host_id else [])
            return tq.TrafficFilters(
                start=s, end=e, host_ids=hosts, backends=backend,
                status_classes=status_class, statuses=status_code,
                status_min=status_min, status_max=status_max, methods=method,
                path=path or None, path_mode=path_mode, client_ip=client_ip or None,
                countries=country, user_agent=ua or None, bot=bot,
                min_response_ms=min_rt, search=search or None,
            )
        except tq.FilterError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return dep


list_filters = traffic_filters(None)
view_filters = traffic_filters("24h")


def _cache_key(name: str, request: Request) -> str:
    items = sorted(request.query_params.multi_items())
    digest = hashlib.sha1(json.dumps(items).encode()).hexdigest()[:20]
    return f"traffic:{name}:{digest}"


# ─── Request list ───────────────────────────────────────────────────────────


@router.get("/", response_model=list[TrafficLogResponse])
async def list_traffic_logs(
    response: Response,
    skip: int = Query(0, ge=0, le=100_000),
    limit: int = Query(50, ge=1, le=100),
    f: tq.TrafficFilters = Depends(list_filters),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Matching requests, newest first.

    X-Total-Count carries the number of matches. It is exact when the filters are
    ones the hourly rollup keeps (time, host, backend, status); otherwise counting
    stops at 10,000 and X-Total-Count-Capped is "true".
    """
    rows = await tq.list_logs(db, f, skip=skip, limit=limit)
    if len(rows) < limit and (rows or skip == 0):
        # A short page is the last one: no need to count (a raw count of a rare
        # match is a second full scan of the window).
        total, capped = skip + len(rows), False
    else:
        total, capped = await tq.count_matching(db, f)
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Total-Count-Capped"] = "true" if capped else "false"
    return [TrafficLogResponse(**r) for r in rows]


# ─── Summaries ──────────────────────────────────────────────────────────────


@router.get("/stats", response_model=TrafficStatsResponse)
async def get_traffic_stats(
    proxy_host_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    include_top_ips: bool = Query(True, description="Top client IPs need a raw scan of the window; the UI skips them"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Totals for the last ``days``, from the hourly rollup plus the live tail.

    avg_response_time leaves out websocket/SSE responses (their duration is how long
    the connection stayed open).
    """
    cache_key = f"traffic:stats2:{proxy_host_id or 'all'}:{days}:{int(include_top_ips)}"

    async def _compute() -> TrafficStatsResponse:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        f = tq.TrafficFilters(start=now - timedelta(days=days), host_ids=[proxy_host_id] if proxy_host_id else [])
        watermark = await tq.rolled_until(db)
        # Day buckets (UTC midnight-aligned) give today / this week exactly.
        rows = await tq.aggregate(db, f, ["proxy_host_id", "status_class"], stride=timedelta(days=1), watermark=watermark)
        totals = tq.merge(rows)
        by_class = {c: 0 for c in (2, 3, 4, 5)}
        per_host: dict[str, int] = {}
        today = week = 0
        for r in rows:
            if r["status_class"] in by_class:
                by_class[r["status_class"]] += r["requests"]
            per_host[r["proxy_host_id"]] = per_host.get(r["proxy_host_id"], 0) + r["requests"]
            if r["bucket"] >= today_start:
                today += r["requests"]
            if r["bucket"] >= week_start:
                week += r["requests"]
        methods = await tq.method_counts(db, f, watermark=watermark)
        top_ids = sorted(per_host, key=lambda h: per_host[h], reverse=True)[:10]
        names = await tn.host_names(db, top_ids)
        top_ips = []
        if include_top_ips:
            top_ips = [{"ip": r["value"], "count": r["requests"]} for r in await tq.top_raw(db, f, "client_ip", limit=10)]
        avg = totals["rt_sum"] / totals["rt_count"] if totals["rt_count"] else None
        return TrafficStatsResponse(
            total_requests=totals["requests"],
            requests_today=today,
            requests_this_week=week,
            requests_by_status={f"{c}xx": n for c, n in by_class.items()},
            requests_by_method={m["value"]: m["requests"] for m in methods},
            avg_response_time=avg,
            total_bytes_sent=totals["bytes_sent"],
            total_bytes_received=totals["bytes_received"],
            top_ips=top_ips,
            top_hosts=[{"host_id": h, "name": names.get(h, "Unknown"), "count": per_host[h]} for h in top_ids],
        )

    # The UI polls every 60s; a TTL that long means one computation per poll
    # interval rather than (with the old 30s TTL) a miss on every poll.
    payload = await cached_json(cache_key, ttl=60, producer=_compute)
    return TrafficStatsResponse(**payload) if isinstance(payload, dict) else payload


@router.get("/overview")
async def traffic_overview(
    request: Request,
    f: tq.TrafficFilters = Depends(view_filters),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Summary cards, status codes and the over-time series for the filters."""

    async def _compute() -> dict:
        now = datetime.now(timezone.utc)
        stride = tq.auto_stride(f.start, f.end, now)
        watermark = await tq.rolled_until(db)
        rows = await tq.aggregate(db, f, ["status"], stride=stride, watermark=watermark)
        totals = tq.merge(rows)
        codes: dict[int, int] = {}
        series: dict[datetime, list[dict]] = {}
        for r in rows:
            codes[r["status"]] = codes.get(r["status"], 0) + r["requests"]
            series.setdefault(r["bucket"], []).append(r)
        e4 = sum(n for c, n in codes.items() if 400 <= c < 500)
        e5 = sum(n for c, n in codes.items() if c >= 500)
        points = []
        for b in tn.buckets(f.start, f.end or now, stride, series):
            rs = series.get(b, [])
            m = tq.merge(rs)
            point = {"t": b.isoformat(), "requests": m["requests"], "bytes_sent": m["bytes_sent"],
                     "bytes_received": m["bytes_received"], **{f"s{c}xx": 0 for c in (1, 2, 3, 4, 5)}}
            for r in rs:
                cls = max(1, min(5, r["status"] // 100))
                point[f"s{cls}xx"] += r["requests"]
            lat = tq.latency_summary(m)
            point.update(avg=lat["avg"], p50=lat["p50"], p95=lat["p95"])
            points.append(point)
        total = totals["requests"]
        return {
            "range": {"start": f.start, "end": f.end, "stride_seconds": int(stride.total_seconds())},
            "rolled_until": watermark,
            "totals": {
                "requests": total, "bot_requests": totals["bot_requests"],
                "bytes_sent": totals["bytes_sent"], "bytes_received": totals["bytes_received"],
                "errors_4xx": e4, "errors_5xx": e5,
                "error_rate": round((e4 + e5) / total * 100, 2) if total else 0.0,
                "server_error_rate": round(e5 / total * 100, 2) if total else 0.0,
                "latency": tq.latency_summary(totals),
                "last_seen": totals["last_seen"],
            },
            "status_codes": [{"status": c, "requests": n} for c, n in sorted(codes.items(), key=lambda kv: -kv[1])],
            "timeseries": points,
        }

    return await cached_json(_cache_key("overview", request), ttl=VIEW_CACHE_TTL, producer=_compute)


TOP_DIMENSIONS = {
    "path", "client_ip", "country", "user_agent", "referer", "method",
    "status", "proxy_host", "backend", "backend_host",
}


@router.get("/top")
async def traffic_top(
    request: Request,
    dimension: str = Query(..., description="path, client_ip, country, user_agent, referer, method, status, proxy_host, backend, backend_host"),
    limit: int = Query(10, ge=1, le=50),
    f: tq.TrafficFilters = Depends(view_filters),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The most frequent values of one field among matching requests."""
    if dimension not in TOP_DIMENSIONS:
        raise HTTPException(status_code=422, detail=f"dimension must be one of {', '.join(sorted(TOP_DIMENSIONS))}")

    async def _compute() -> list[dict]:
        if dimension in tq.TOP_RAW:
            items = await tq.top_raw(db, f, dimension, limit=limit)
            if dimension == "client_ip":
                labels = await tn.known_labels(db, [i["value"] for i in items])
                for i in items:
                    i["known_label"] = labels.get(i["value"])
            return items
        if dimension == "method":
            return await tq.method_counts(db, f, limit=limit)
        dim = {"status": "status", "proxy_host": "proxy_host_id", "backend": "upstream", "backend_host": "upstream_host"}[dimension]
        rows = await tq.aggregate(db, f, [dim, "status_class"])
        grouped: dict = {}
        for r in rows:
            grouped.setdefault(r[dim], []).append(r)
        items = []
        for value, rs in grouped.items():
            m = tq.merge(rs)
            items.append({
                "value": value, "label": None, "requests": m["requests"],
                "errors_4xx": sum(r["requests"] for r in rs if r["status_class"] == 4),
                "errors_5xx": sum(r["requests"] for r in rs if r["status_class"] == 5),
                "avg_response_time": tq.latency_summary(m)["avg"],
                "bytes_sent": m["bytes_sent"], "last_seen": m["last_seen"],
            })
        items.sort(key=lambda i: -i["requests"])
        items = items[:limit]
        if dimension == "proxy_host":
            names = await tn.host_names(db, [i["value"] for i in items])
            for i in items:
                i["label"] = names.get(i["value"])
        return items

    return await cached_json(_cache_key("top", request), ttl=VIEW_CACHE_TTL, producer=_compute)


@router.get("/backends")
async def traffic_backends(
    request: Request,
    group: str = Query("host", pattern="^(host|hostport)$", description="host: one row per machine; hostport: per upstream"),
    limit: int = Query(200, ge=1, le=500),
    f: tq.TrafficFilters = Depends(view_filters),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every backend (upstream) that served matching requests, with its figures."""

    async def _compute() -> list[dict]:
        dim = "upstream_host" if group == "host" else "upstream"
        rows = await tq.aggregate(db, f, [dim, "proxy_host_id", "status_class"])
        by_backend: dict[str, list[dict]] = {}
        for r in rows:
            by_backend.setdefault(r[dim], []).append(r)
        names = await tn.host_names(db, list({r["proxy_host_id"] for r in rows}))
        meta = await tn.backend_meta(db, list(by_backend))
        out = []
        for backend, rs in by_backend.items():
            m = tq.merge(rs)
            hosts: dict[str, int] = {}
            for r in rs:
                hosts[r["proxy_host_id"]] = hosts.get(r["proxy_host_id"], 0) + r["requests"]
            e4 = sum(r["requests"] for r in rs if r["status_class"] == 4)
            e5 = sum(r["requests"] for r in rs if r["status_class"] == 5)
            lat = tq.latency_summary(m)
            total = m["requests"]
            out.append({
                "backend": backend,  # '' = answered by the proxy itself (no upstream)
                "requests": total,
                "errors_4xx": e4, "errors_5xx": e5,
                "error_rate": round((e4 + e5) / total * 100, 2) if total else 0.0,
                "server_error_rate": round(e5 / total * 100, 2) if total else 0.0,
                "p50": lat["p50"], "p95": lat["p95"], "avg": lat["avg"],
                "bytes_sent": m["bytes_sent"], "bytes_received": m["bytes_received"],
                "last_seen": m["last_seen"],
                "hosts": sorted(
                    [{"id": h, "name": names.get(h, "Unknown"), "requests": n} for h, n in hosts.items()],
                    key=lambda x: -x["requests"],
                ),
                **meta.get(tn.host_part(backend), tn.empty_meta()),
            })
        out.sort(key=lambda b: -b["requests"])
        return out[:limit]

    return await cached_json(_cache_key("backends", request), ttl=VIEW_CACHE_TTL, producer=_compute)


@router.get("/nodes")
async def traffic_nodes(
    request: Request,
    f: tq.TrafficFilters = Depends(view_filters),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """How matching traffic spread over upstream nodes (host:port): each node's
    share, errors, latency and failovers, the share over time, and which node
    requests fell back from and to. Meant for a load-balanced host (filter by host)
    or one machine (filter by backend)."""

    async def _compute() -> dict:
        return await tn.node_summary(db, f, now=datetime.now(timezone.utc))

    return await cached_json(_cache_key("nodes", request), ttl=VIEW_CACHE_TTL, producer=_compute)


@router.get("/backend-info")
async def backend_info(
    backend: str = Query(..., min_length=1, max_length=255),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """What we know about a backend outside the logs: its known-IP label, the proxy
    hosts configured to send to it, and upstream health where that is tracked."""
    meta = await tn.backend_meta(db, [backend])
    return {"backend": backend, **meta.get(tn.host_part(backend), tn.empty_meta())}


@router.get("/client-info")
async def client_info(
    ip: str = Query(..., min_length=2, max_length=64),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Enrichment, known-IP label and threat status for one client address."""
    enr = (await db.execute(select(IpEnrichment).where(IpEnrichment.ip_address == ip))).scalar_one_or_none()
    known = (await db.execute(select(KnownIp).where(KnownIp.ip_address == ip))).scalar_one_or_none()
    actor = (await db.execute(select(ThreatActor).where(ThreatActor.ip_address == ip))).scalar_one_or_none()
    return {
        "ip": ip,
        "known": {"label": known.label, "category": known.category, "trusted": known.trusted} if known else None,
        "enrichment": {
            k: getattr(enr, k) for k in (
                "country_code", "country_name", "city", "region", "isp", "org", "asn", "as_name",
                "reverse_dns", "abuse_score", "is_tor", "is_proxy", "is_vpn", "is_datacenter", "is_crawler",
            )
        } if enr else None,
        "threat": {
            "status": actor.current_status, "score": actor.threat_score,
            "events": actor.total_events, "last_seen": actor.last_seen,
        } if actor else None,
    }


# ─── Geo, enrichment (behaviour unchanged) ──────────────────────────────────


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
        select(TrafficLog.country_code, TrafficLog.country_name, func.count(TrafficLog.id).label("count"))
        .where(TrafficLog.country_code.isnot(None), TrafficLog.timestamp >= since)
        .group_by(TrafficLog.country_code, TrafficLog.country_name)
        .order_by(func.count(TrafficLog.id).desc())
    )
    if proxy_host_id:
        query = query.where(TrafficLog.proxy_host_id == proxy_host_id)
    rows = (await db.execute(query)).all()
    return [{"country_code": r[0], "country_name": r[1] or r[0], "count": r[2]} for r in rows]


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
            IpEnrichment.city, IpEnrichment.country_code, IpEnrichment.country_name,
            IpEnrichment.latitude, IpEnrichment.longitude,
            func.count(TrafficLog.id).label("count"),
            func.count(func.distinct(TrafficLog.client_ip)).label("unique_ips"),
        )
        .join(IpEnrichment, TrafficLog.client_ip == IpEnrichment.ip_address)
        .where(and_(*base_filter))
        .group_by(IpEnrichment.city, IpEnrichment.country_code, IpEnrichment.country_name,
                  IpEnrichment.latitude, IpEnrichment.longitude)
        .order_by(func.count(TrafficLog.id).desc())
        .limit(200)
    )
    result = await db.execute(query)
    return [
        {"city": r[0] or "Unknown", "country_code": r[1], "country_name": r[2],
         "lat": float(r[3]), "lon": float(r[4]), "count": r[5], "unique_ips": r[6]}
        for r in result.all()
    ]


@router.get("/enrichment/status")
async def get_enrichment_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the status of IP enrichment backfill — how many IPs still need enrichment."""
    subq = select(IpEnrichment.ip_address)
    total = (await db.execute(
        select(func.count(func.distinct(TrafficLog.client_ip))).where(TrafficLog.client_ip.isnot(None))
    )).scalar() or 0
    enriched = (await db.execute(
        select(func.count(func.distinct(TrafficLog.client_ip)))
        .where(TrafficLog.client_ip.isnot(None), TrafficLog.client_ip.in_(subq))
    )).scalar() or 0
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
    return await backfill_enrichment(db, batch_size=40)


# ─── One request ────────────────────────────────────────────────────────────

_SECRET_HEADERS = {"cookie", "authorization", "proxy-authorization", "x-api-key", "x-internal-auth"}


def _safe_headers(raw: Optional[str]) -> Optional[dict]:
    """Logged request headers, minus credentials."""
    if not raw:
        return None
    try:
        headers = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(headers, dict):
        return None
    return {k: ("[redacted]" if str(k).lower() in _SECRET_HEADERS else v) for k, v in headers.items()}


@router.get("/{log_id}")
async def get_traffic_log(
    log_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Everything logged for one request, plus what we know about its client and
    backend, and any WAF/threat events for the same client around that moment."""
    log = (await db.execute(select(TrafficLog).where(TrafficLog.id == log_id))).scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Traffic log not found")
    names = await tn.host_names(db, [log.proxy_host_id])
    enr = (await db.execute(select(IpEnrichment).where(IpEnrichment.ip_address == log.client_ip))).scalar_one_or_none()
    known = await tn.known_labels(db, [log.client_ip])
    events = []
    if log.timestamp:
        window = timedelta(seconds=5)
        evs = (await db.execute(
            select(ThreatEvent)
            .where(ThreatEvent.client_ip == log.client_ip,
                   ThreatEvent.timestamp >= log.timestamp - window,
                   ThreatEvent.timestamp <= log.timestamp + window)
            .order_by(ThreatEvent.timestamp).limit(20)
        )).scalars().all()
        events = [
            {"id": e.id, "timestamp": e.timestamp, "category": e.category, "rule_name": e.rule_name,
             "rule_id": e.rule_id, "severity": e.severity, "action_taken": e.action_taken,
             "request_uri": e.request_uri, "matched_payload": (e.matched_payload or "")[:500]}
            for e in evs
        ]
    upstream = tq.host_of(log.upstream_addr.split(",")[-1].strip()) if log.upstream_addr else None
    backend = (await tn.backend_meta(db, [upstream])).get(upstream) if upstream else None
    base = TrafficLogResponse(
        **{c: getattr(log, c) for c in tq.LIST_COLUMNS},
        host_name=names.get(log.proxy_host_id),
        city=enr.city if enr else None,
    ).model_dump()
    return {
        **base,
        "request_headers": _safe_headers(log.request_headers),
        "client": {
            "known_label": known.get(log.client_ip),
            "isp": enr.isp if enr else None, "org": enr.org if enr else None,
            "asn": enr.asn if enr else None, "reverse_dns": enr.reverse_dns if enr else None,
            "region": enr.region if enr else None,
        },
        "backend": {"host": upstream, **backend} if backend else None,
        "attempts": _attempt_chain(log),
        "security_events": events,
    }


def _attempt_chain(log: TrafficLog) -> list[dict]:
    """The upstreams nginx tried for this request, in order.

    Uses the load-balancing log (upstream_attempt_log: [{"addr", "status", "ms"}],
    written when nginx tried more than one server); otherwise the addresses in
    upstream_addr, where only the final attempt's status and time are known.
    """
    raw = getattr(log, "upstream_attempt_log", None)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if isinstance(raw, list) and raw:
        return [
            {
                "node": a.get("addr") if isinstance(a, dict) else str(a),
                "status": a.get("status") if isinstance(a, dict) else None,
                "time_ms": a.get("ms") if isinstance(a, dict) else None,
                "final": i == len(raw) - 1,
            }
            for i, a in enumerate(raw)
        ]
    final_status = getattr(log, "upstream_status", None) or log.status
    addrs = [a.strip() for a in (log.upstream_addr or "").split(",") if a.strip()]
    return [
        {
            "node": a,
            "status": final_status if i == len(addrs) - 1 else None,
            "time_ms": log.upstream_response_time if i == len(addrs) - 1 else None,
            "final": i == len(addrs) - 1,
        }
        for i, a in enumerate(addrs)
    ]


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_traffic_log(
    log_id: str,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single traffic log entry (admins only: the log is an audit trail)."""
    log = (await db.execute(select(TrafficLog).where(TrafficLog.id == log_id))).scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Traffic log not found")
    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="traffic_log_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted traffic log {log_id}",
    ))
    ts = log.timestamp
    await db.delete(log)
    await db.flush()
    if ts:
        # Keep the hourly summary for that hour equal to the rows that remain.
        await traffic_rollup_service.rebuild_hour_of(db, ts)
    await db.commit()


@router.delete("", status_code=status.HTTP_200_OK)
async def purge_traffic_logs(
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Purge all traffic logs (admins only)."""
    count = (await db.execute(text("SELECT count(*) FROM traffic_logs"))).scalar() or 0
    await db.execute(sa_delete(TrafficLog))
    await traffic_rollup_service.clear(db)
    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="traffic_logs_purged",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Purged all traffic logs ({count} records)",
    ))
    await db.commit()
    return {"status": "ok", "deleted": count}
