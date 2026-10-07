"""Filtering and aggregation for the Traffic page.

Every Traffic view is "these filters, aggregated by these dimensions". This module
turns a :class:`TrafficFilters` into SQL and answers it from the cheapest source:

- ``traffic_rollup_hourly`` for whole hours already summarised (see
  traffic_rollup_service), when every filter is one the rollup keeps (time, proxy
  host, backend, status) and the time buckets are whole hours;
- ``traffic_logs`` for everything else: the partial hours at either end of the
  window, the tail not yet rolled up, and any filter on fields the rollup drops
  (path, client IP, country, user agent, bot, latency, method, free text).

Both halves are aggregated in one statement (UNION ALL, then summed), so a
request is counted exactly once whichever side it comes from.

Response-time percentiles come from a fixed latency histogram
(LATENCY_BOUNDS_MS) on both sides, so they are estimates: within one bucket,
interpolated linearly. Long-lived websocket/SSE responses are left out of
latency figures (their "response time" is how long someone stayed connected).

All SQL is built from fixed fragments; every value is a bound parameter.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.traffic_log import UPSTREAM_HOST_SQL, UPSTREAM_SQL

# Histogram bucket bounds, milliseconds. width_bucket() puts a value below the
# first bound in slot 0 and one at/above the last in slot len(bounds).
LATENCY_BOUNDS_MS: tuple[int, ...] = (
    1, 2, 5, 10, 20, 50, 100, 200, 300, 500, 750,
    1000, 1500, 2000, 3000, 5000, 10000, 30000, 60000,
)
HIST_LEN = len(LATENCY_BOUNDS_MS) + 1
_BOUNDS_SQL = "'{" + ",".join(str(b) for b in LATENCY_BOUNDS_MS) + "}'::int[]"
# Slot of a row's response time, NULL when it has none or is a stream.
WB_SQL = (
    "CASE WHEN response_time IS NOT NULL AND is_streaming IS NOT TRUE "
    f"THEN width_bucket(response_time, {_BOUNDS_SQL}) END"
)

# nginx lists every upstream it tried ("a:80, b:80"); more than one means the
# request failed over to another node.
FAILOVER_SQL = "(upstream_failover IS TRUE OR upstream_addr LIKE '%,%')"

# A raw (non-rollup) query never runs longer than this. The page asks for
# bounded windows, but a 90-day free-text search could otherwise pin a
# connection for minutes.
RAW_STATEMENT_TIMEOUT_MS = 20_000

# Counting matches of a filter the rollup can't answer stops here.
COUNT_CAP = 10_000

ORIGIN = datetime(2000, 1, 3, tzinfo=timezone.utc)  # a Monday, UTC midnight

_PRESETS = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}
BACKEND_WITH_PORT = re.compile(r"^(\[[0-9A-Fa-f:.]+\]|[^:\s]+):\d{1,5}$")


class FilterError(ValueError):
    """A filter value that can't be used (bad IP/CIDR, unknown preset, …)."""


def floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def ceil_hour(dt: datetime) -> datetime:
    f = floor_hour(dt)
    return f if f == dt else f + timedelta(hours=1)


def resolve_range(
    range_: Optional[str], start: Optional[datetime], end: Optional[datetime],
    *, default: Optional[str] = "24h", now: Optional[datetime] = None,
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Turn a preset ("24h") or explicit start/end into aware UTC datetimes."""
    now = now or datetime.now(timezone.utc)
    if start or end:
        s = _aware(start) if start else None
        e = _aware(end) if end else None
        if s and e and s >= e:
            raise FilterError("start must be before end")
        return s, e
    key = range_ or default
    if key is None or key == "all":
        return None, None
    if key not in _PRESETS:
        raise FilterError(f"Unknown range {key!r}")
    return now - _PRESETS[key], None


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


@dataclass
class TrafficFilters:
    start: Optional[datetime] = None  # inclusive
    end: Optional[datetime] = None    # exclusive; None = now
    host_ids: list[str] = field(default_factory=list)
    # Backends: "10.0.0.5:8080" matches that upstream exactly, "10.0.0.5" every
    # port on that machine.
    backends: list[str] = field(default_factory=list)
    status_classes: list[int] = field(default_factory=list)  # 1..5
    statuses: list[int] = field(default_factory=list)
    status_min: Optional[int] = None  # legacy range filter
    status_max: Optional[int] = None
    methods: list[str] = field(default_factory=list)
    path: Optional[str] = None
    path_mode: str = "contains"  # contains | prefix
    client_ip: Optional[str] = None  # address or CIDR
    countries: list[str] = field(default_factory=list)
    user_agent: Optional[str] = None
    bot: Optional[bool] = None
    min_response_ms: Optional[int] = None
    search: Optional[str] = None  # legacy free text: URI, client IP, user agent

    def __post_init__(self) -> None:
        if self.path_mode not in ("contains", "prefix"):
            raise FilterError("path_mode must be 'contains' or 'prefix'")
        for c in self.status_classes:
            if c not in (1, 2, 3, 4, 5):
                raise FilterError("status class must be 1-5")
        if self.client_ip:
            v = self.client_ip.strip()
            try:
                if "/" in v:
                    ipaddress.ip_network(v, strict=False)
                else:
                    ipaddress.ip_address(v)
            except ValueError as e:
                raise FilterError(f"Not an IP address or CIDR range: {v!r}") from e
            self.client_ip = v
        self.countries = [c.strip().upper() for c in self.countries if c.strip()]
        self.methods = [m.strip().upper() for m in self.methods if m.strip()]
        self.backends = [b.strip() for b in self.backends if b.strip()]

    # Filters the hourly rollup can answer.
    @property
    def rollup_compatible(self) -> bool:
        # The rollup keeps the exact status code, so status classes, codes and the
        # legacy min/max range all work on it.
        return (
            not self.methods
            and not self.path
            and not self.client_ip
            and not self.countries
            and not self.user_agent
            and self.bot is None
            and self.min_response_ms is None
            and not self.search
        )

    @property
    def method_rollup_compatible(self) -> bool:
        """The per-method rollup keeps only time and proxy host."""
        return (
            self.status_min is None and self.status_max is None
            and not self.status_classes and not self.statuses and not self.backends
            and not self.path and not self.client_ip and not self.countries
            and not self.user_agent and self.bot is None and self.min_response_ms is None
            and not self.search
        )


# ─── SQL fragments ──────────────────────────────────────────────────────────


def _like_escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class _Params(dict):
    def add(self, value: Any) -> str:
        name = f"p{len(self)}"
        self[name] = value
        return f":{name}"


def _dimension_filters(f: TrafficFilters, p: _Params, *, rollup: bool) -> list[str]:
    """Predicates on host / backend / status, for either side."""
    out: list[str] = []
    if f.host_ids:
        out.append(f"proxy_host_id = ANY(CAST({p.add(list(f.host_ids))} AS varchar[]))")
    if f.backends:
        exact = [b for b in f.backends if BACKEND_WITH_PORT.match(b)]
        hosts = [b for b in f.backends if not BACKEND_WITH_PORT.match(b)]
        up = "upstream" if rollup else UPSTREAM_SQL
        up_host = "regexp_replace(upstream, ':[0-9]+$', '')" if rollup else UPSTREAM_HOST_SQL
        parts = []
        if hosts:
            parts.append(f"{up_host} = ANY(CAST({p.add(hosts)} AS text[]))")
        if exact:
            # The host-part comparison lets the raw side use the expression index.
            parts.append(
                f"({up_host} = ANY(CAST({p.add([host_of(b) for b in exact])} AS text[])) "
                f"AND {up} = ANY(CAST({p.add(exact)} AS text[])))"
            )
        out.append("(" + " OR ".join(parts) + ")")
    status_parts = []
    if f.status_classes:
        status_parts.append(f"status / 100 = ANY(CAST({p.add(list(f.status_classes))} AS int[]))")
    if f.statuses:
        status_parts.append(f"status = ANY(CAST({p.add(list(f.statuses))} AS int[]))")
    if status_parts:
        out.append("(" + " OR ".join(status_parts) + ")")
    if f.status_min is not None:
        out.append(f"status >= {p.add(f.status_min)}")
    if f.status_max is not None:
        out.append(f"status <= {p.add(f.status_max)}")
    return out


def host_of(backend: str) -> str:
    return re.sub(r":[0-9]+$", "", backend)


def _raw_only_filters(f: TrafficFilters, p: _Params) -> list[str]:
    out: list[str] = []
    if f.methods:
        out.append(f"request_method = ANY(CAST({p.add(f.methods)} AS varchar[]))")
    if f.path:
        if f.path_mode == "prefix":
            out.append(f"request_uri LIKE {p.add(_like_escape(f.path) + '%')}")
        else:
            out.append(f"request_uri ILIKE {p.add('%' + _like_escape(f.path) + '%')}")
    if f.client_ip:
        if "/" in f.client_ip:
            # client_ip is text; the guard keeps a malformed value from failing the cast.
            out.append(
                "(CASE WHEN client_ip ~ '^[0-9A-Fa-f:.]+$' THEN client_ip::inet END) "
                f"<<= CAST({p.add(f.client_ip)} AS cidr)"
            )
        else:
            out.append(f"client_ip = {p.add(f.client_ip)}")
    if f.countries:
        out.append(f"country_code = ANY(CAST({p.add(f.countries)} AS varchar[]))")
    if f.user_agent:
        out.append(f"user_agent ILIKE {p.add('%' + _like_escape(f.user_agent) + '%')}")
    if f.bot is True:
        out.append("is_bot IS TRUE")
    elif f.bot is False:
        out.append("is_bot IS NOT TRUE")
    if f.min_response_ms is not None:
        out.append(f"response_time >= {p.add(int(f.min_response_ms))}")
    if f.search and f.search.strip():
        term = p.add("%" + _like_escape(f.search.strip()) + "%")
        out.append(f"(request_uri ILIKE {term} OR client_ip ILIKE {term} OR user_agent ILIKE {term})")
    return out


def raw_where(f: TrafficFilters, p: _Params, ranges: Optional[list[tuple]] = None) -> str:
    """WHERE body over traffic_logs (unqualified columns) for the filters.

    ``ranges`` replaces the filter's own time window with explicit [start, end)
    pieces (used for the parts of a window the rollup doesn't cover).
    """
    preds = _dimension_filters(f, p, rollup=False) + _raw_only_filters(f, p)
    if ranges is None:
        ranges = [(f.start, f.end)]
    time_parts = []
    for s, e in ranges:
        bits = []
        if s is not None:
            bits.append(f"timestamp >= {p.add(s)}")
        if e is not None:
            bits.append(f"timestamp < {p.add(e)}")
        time_parts.append("(" + " AND ".join(bits) + ")" if bits else "TRUE")
    if len(time_parts) == 1:
        if time_parts[0] != "TRUE":
            preds.insert(0, time_parts[0])
    else:
        preds.insert(0, "(" + " OR ".join(time_parts) + ")")
    return " AND ".join(preds) if preds else "TRUE"


# ─── Rollup coverage ────────────────────────────────────────────────────────


async def rolled_until(db: AsyncSession) -> Optional[datetime]:
    try:
        return (await db.execute(text("SELECT rolled_until FROM traffic_rollup_state WHERE id = 1"))).scalar()
    except Exception:  # noqa: BLE001 — table missing on a half-migrated DB: just use raw rows
        await db.rollback()
        return None


@dataclass
class _Plan:
    rollup: Optional[tuple[Optional[datetime], datetime]]  # [start, end) of buckets, start None = all
    raw: list[tuple[Optional[datetime], Optional[datetime]]]


def plan_sources(
    f: TrafficFilters, watermark: Optional[datetime], *, stride: Optional[timedelta] = None,
    rollup_ok: bool = True,
) -> _Plan:
    """Split the window between the rollup (whole, summarised hours) and raw rows."""
    whole = [(f.start, f.end)]
    if not rollup_ok or watermark is None or not f.rollup_compatible:
        return _Plan(None, whole)
    if stride is not None and (stride < timedelta(hours=1) or stride % timedelta(hours=1)):
        return _Plan(None, whole)
    rs = ceil_hour(f.start) if f.start else None
    re_ = min(floor_hour(f.end), watermark) if f.end else watermark
    if rs is not None and rs >= re_:
        return _Plan(None, whole)
    raw: list[tuple[Optional[datetime], Optional[datetime]]] = []
    if f.start is not None and f.start < rs:
        raw.append((f.start, rs))
    raw.append((re_, f.end))
    return _Plan((rs, re_), raw)


# ─── Aggregation ────────────────────────────────────────────────────────────

# name -> (raw expression, rollup expression)
DIMENSIONS: dict[str, tuple[str, str]] = {
    "proxy_host_id": ("proxy_host_id", "proxy_host_id"),
    "upstream": (UPSTREAM_SQL, "upstream"),
    "upstream_host": (UPSTREAM_HOST_SQL, "regexp_replace(upstream, ':[0-9]+$', '')"),
    "status": ("status", "status"),
    "status_class": ("status / 100", "status / 100"),
}


def _measure_cols_raw() -> list[str]:
    cols = [
        "count(*) AS requests",
        "count(*) FILTER (WHERE is_bot IS TRUE) AS bot_requests",
        "count(*) FILTER (WHERE failover) AS failovers",
        "coalesce(sum(bytes_sent), 0) AS bytes_sent",
        "coalesce(sum(bytes_received), 0) AS bytes_received",
        "count(wb) AS rt_count",
        "coalesce(sum(response_time) FILTER (WHERE wb IS NOT NULL), 0) AS rt_sum",
        "max(timestamp) AS last_seen",
    ]
    cols += [f"count(*) FILTER (WHERE wb = {i}) AS h{i}" for i in range(HIST_LEN)]
    return cols


def _measure_cols_rollup() -> list[str]:
    cols = [
        "sum(requests) AS requests", "sum(bot_requests) AS bot_requests", "sum(failovers) AS failovers",
        "sum(bytes_sent) AS bytes_sent", "sum(bytes_received) AS bytes_received",
        "sum(rt_count) AS rt_count", "sum(rt_sum) AS rt_sum", "max(last_seen) AS last_seen",
    ]
    cols += [f"sum(rt_hist[{i + 1}]) AS h{i}" for i in range(HIST_LEN)]
    return cols


_OUTER_MEASURES = (
    ["sum(requests)::bigint AS requests", "sum(bot_requests)::bigint AS bot_requests",
     "sum(failovers)::bigint AS failovers",
     "sum(bytes_sent)::bigint AS bytes_sent", "sum(bytes_received)::bigint AS bytes_received",
     "sum(rt_count)::bigint AS rt_count", "sum(rt_sum)::bigint AS rt_sum", "max(last_seen) AS last_seen"]
    + [f"sum(h{i})::bigint AS h{i}" for i in range(HIST_LEN)]
)


async def aggregate(
    db: AsyncSession,
    f: TrafficFilters,
    dims: Iterable[str] = (),
    *,
    stride: Optional[timedelta] = None,
    order: str = "requests",
    limit: Optional[int] = None,
    watermark: Optional[datetime] = None,
    use_rollup: bool = True,
) -> list[dict]:
    """Aggregate requests for ``f`` grouped by ``dims`` (and time, if ``stride``).

    Each row: the dims, ``bucket`` when stride is given, and requests,
    bot_requests, bytes_sent, bytes_received, rt_count, rt_sum, last_seen, hist.
    """
    dims = list(dims)
    for d in dims:
        if d not in DIMENSIONS:
            raise ValueError(f"unknown dimension {d}")
    if watermark is None and use_rollup:
        watermark = await rolled_until(db)
    plan = plan_sources(f, watermark, stride=stride, rollup_ok=use_rollup)
    p = _Params()

    def select_dims(rollup: bool) -> list[str]:
        cols = []
        if stride is not None:
            src = "bucket" if rollup else "timestamp"
            cols.append(f"date_bin(CAST({p.add(stride)} AS interval), {src}, CAST({p.add(ORIGIN)} AS timestamptz)) AS bucket")
        for d in dims:
            cols.append(f"{DIMENSIONS[d][1 if rollup else 0]} AS {d}")
        return cols

    group_names = (["bucket"] if stride is not None else []) + dims
    group_idx = ", ".join(str(i + 1) for i in range(len(group_names)))
    parts = []
    if plan.rollup is not None:
        rs, re_ = plan.rollup
        where = _dimension_filters(f, p, rollup=True)
        if rs is not None:
            where.append(f"bucket >= {p.add(rs)}")
        where.append(f"bucket < {p.add(re_)}")
        cols = select_dims(True) + _measure_cols_rollup()
        parts.append(
            f"SELECT {', '.join(cols)} FROM traffic_rollup_hourly WHERE {' AND '.join(where)}"
            + (f" GROUP BY {group_idx}" if group_names else "")
        )
    raw_dims = select_dims(False)
    raw_dim_names = (["bucket"] if stride is not None else []) + dims
    inner = (
        f"SELECT {', '.join(raw_dims + ['timestamp', 'is_bot', FAILOVER_SQL + ' AS failover', 'bytes_sent', 'bytes_received', 'response_time', WB_SQL + ' AS wb'])} "
        f"FROM traffic_logs WHERE {raw_where(f, p, plan.raw)}"
    )
    raw_cols = raw_dim_names + _measure_cols_raw()
    parts.append(
        f"SELECT {', '.join(raw_cols)} FROM ({inner}) r"
        + (f" GROUP BY {group_idx}" if group_names else "")
    )
    union = " UNION ALL ".join(f"({q})" for q in parts)
    outer_cols = group_names + _OUTER_MEASURES
    sql = f"SELECT {', '.join(outer_cols)} FROM ({union}) u"
    if group_names:
        sql += f" GROUP BY {', '.join(group_names)}"
    if order == "bucket" and stride is not None:
        sql += " ORDER BY bucket"
    elif group_names:
        sql += " ORDER BY requests DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    await _raw_timeout(db)
    rows = (await db.execute(text(sql), dict(p))).mappings().all()
    out = []
    for r in rows:
        d = {k: r[k] for k in group_names}
        d.update(
            requests=int(r["requests"] or 0), bot_requests=int(r["bot_requests"] or 0),
            failovers=int(r["failovers"] or 0),
            bytes_sent=int(r["bytes_sent"] or 0), bytes_received=int(r["bytes_received"] or 0),
            rt_count=int(r["rt_count"] or 0), rt_sum=int(r["rt_sum"] or 0),
            last_seen=r["last_seen"], hist=[int(r[f"h{i}"] or 0) for i in range(HIST_LEN)],
        )
        out.append(d)
    return out


async def _raw_timeout(db: AsyncSession) -> None:
    await db.execute(text(f"SET LOCAL statement_timeout = {RAW_STATEMENT_TIMEOUT_MS}"))


async def method_counts(db: AsyncSession, f: TrafficFilters, *, watermark: Optional[datetime] = None,
                        limit: int = 20) -> list[dict]:
    """Requests per method; from the method rollup when only time/host filter."""
    if watermark is None:
        watermark = await rolled_until(db)
    plan = plan_sources(f, watermark if f.method_rollup_compatible else None)
    p = _Params()
    parts = []
    if plan.rollup is not None:
        rs, re_ = plan.rollup
        where = []
        if f.host_ids:
            where.append(f"proxy_host_id = ANY(CAST({p.add(list(f.host_ids))} AS varchar[]))")
        if rs is not None:
            where.append(f"bucket >= {p.add(rs)}")
        where.append(f"bucket < {p.add(re_)}")
        parts.append(
            "SELECT request_method AS value, sum(requests) AS requests FROM traffic_rollup_method_hourly "
            f"WHERE {' AND '.join(where)} GROUP BY 1"
        )
    parts.append(
        "SELECT request_method AS value, count(*) AS requests FROM traffic_logs "
        f"WHERE {raw_where(f, p, plan.raw)} GROUP BY 1"
    )
    sql = (
        "SELECT value, sum(requests)::bigint AS requests FROM ("
        + " UNION ALL ".join(f"({q})" for q in parts)
        + f") u GROUP BY value ORDER BY requests DESC LIMIT {int(limit)}"
    )
    await _raw_timeout(db)
    rows = (await db.execute(text(sql), dict(p))).all()
    return [{"value": r[0], "requests": int(r[1])} for r in rows]


# Raw-only "top N" dimensions: value expression, extra label expression.
TOP_RAW: dict[str, tuple[str, Optional[str]]] = {
    "path": ("request_uri", None),
    "client_ip": ("client_ip", "max(country_code)"),
    "country": ("coalesce(country_code, '')", "max(country_name)"),
    "user_agent": ("coalesce(user_agent, '')", None),
    "referer": ("referer", None),
}


async def top_raw(db: AsyncSession, f: TrafficFilters, dimension: str, *, limit: int = 10) -> list[dict]:
    """Top values of a field the rollup doesn't keep, over raw rows in the window."""
    expr, label = TOP_RAW[dimension]
    p = _Params()
    where = raw_where(f, p)
    if dimension == "referer":
        where += " AND referer IS NOT NULL AND referer <> ''"
    cols = [
        f"{expr} AS value",
        "count(*) AS requests",
        "count(*) FILTER (WHERE status >= 400 AND status < 500) AS errors_4xx",
        "count(*) FILTER (WHERE status >= 500) AS errors_5xx",
        "avg(response_time) FILTER (WHERE is_streaming IS NOT TRUE) AS avg_rt",
        "coalesce(sum(bytes_sent), 0) AS bytes_sent",
        "max(timestamp) AS last_seen",
        f"{label or 'NULL'} AS label",
    ]
    sql = (
        f"SELECT {', '.join(cols)} FROM traffic_logs WHERE {where} "
        f"GROUP BY 1 ORDER BY requests DESC LIMIT {int(limit)}"
    )
    await _raw_timeout(db)
    rows = (await db.execute(text(sql), dict(p))).mappings().all()
    return [
        {
            "value": r["value"], "label": r["label"], "requests": int(r["requests"]),
            "errors_4xx": int(r["errors_4xx"]), "errors_5xx": int(r["errors_5xx"]),
            "avg_response_time": float(r["avg_rt"]) if r["avg_rt"] is not None else None,
            "bytes_sent": int(r["bytes_sent"]), "last_seen": r["last_seen"],
        }
        for r in rows
    ]


async def failover_pairs(db: AsyncSession, f: TrafficFilters, *, limit: int = 20) -> list[dict]:
    """Requests that failed over: each failed upstream → the one that answered.

    "a:80, b:80, c:80" counts a→c and b→c. Raw rows only (bounded by the window);
    a failover is rare, so this reads few rows past the time/host filters.
    """
    p = _Params()
    where = raw_where(f, p)
    sql = (
        "SELECT trim(a.addr) AS from_node, "
        f"{UPSTREAM_SQL} AS to_node, count(*) AS requests "
        "FROM traffic_logs, LATERAL unnest(string_to_array(upstream_addr, ',')) WITH ORDINALITY AS a(addr, n) "
        f"WHERE {where} AND {FAILOVER_SQL} "
        "AND a.n < array_length(string_to_array(upstream_addr, ','), 1) "
        f"GROUP BY 1, 2 ORDER BY requests DESC LIMIT {int(limit)}"
    )
    await _raw_timeout(db)
    rows = (await db.execute(text(sql), dict(p))).mappings().all()
    return [{"from": r["from_node"], "to": r["to_node"], "requests": int(r["requests"])} for r in rows]


async def count_matching(db: AsyncSession, f: TrafficFilters, *, watermark: Optional[datetime] = None) -> tuple[int, bool]:
    """Total rows matching ``f``: exact from the rollup when it can answer,
    otherwise a raw count capped at COUNT_CAP. Returns (count, capped)."""
    if f.rollup_compatible:
        if watermark is None:
            watermark = await rolled_until(db)
        rows = await aggregate(db, f, (), watermark=watermark)
        return (rows[0]["requests"] if rows else 0), False
    p = _Params()
    sql = f"SELECT count(*) FROM (SELECT 1 FROM traffic_logs WHERE {raw_where(f, p)} LIMIT {COUNT_CAP + 1}) s"
    await _raw_timeout(db)
    n = int((await db.execute(text(sql), dict(p))).scalar() or 0)
    return min(n, COUNT_CAP), n > COUNT_CAP


LIST_COLUMNS = (
    "id", "proxy_host_id", "timestamp", "client_ip", "request_method", "request_uri",
    "query_string", "status", "response_time", "bytes_sent", "bytes_received",
    "upstream_addr", "upstream_response_time", "ssl_protocol", "ssl_cipher",
    "user_agent", "referer", "country_code", "country_name", "auth_user", "is_bot", "is_streaming",
)


async def list_logs(db: AsyncSession, f: TrafficFilters, *, skip: int, limit: int) -> list[dict]:
    """Newest-first page of matching requests, with host name and city."""
    p = _Params()
    cols = ", ".join(LIST_COLUMNS)
    sql = (
        f"WITH page AS (SELECT {cols} FROM traffic_logs WHERE {raw_where(f, p)} "
        f"ORDER BY timestamp DESC, id DESC LIMIT {int(limit)} OFFSET {int(skip)}) "
        "SELECT page.*, e.city AS city, (h.domain_names ->> 0) AS host_name "
        "FROM page LEFT JOIN ip_enrichments e ON e.ip_address = page.client_ip "
        "LEFT JOIN proxy_hosts h ON h.id = page.proxy_host_id "
        "ORDER BY page.timestamp DESC, page.id DESC"
    )
    await _raw_timeout(db)
    return [dict(r) for r in (await db.execute(text(sql), dict(p))).mappings().all()]


# ─── Derived figures ────────────────────────────────────────────────────────


def percentile(hist: list[int], q: float) -> Optional[float]:
    """Estimate the q-quantile (0..1) of response time from a histogram."""
    total = sum(hist)
    if total <= 0:
        return None
    target = q * total
    cum = 0
    for i, c in enumerate(hist):
        if c and cum + c >= target:
            lo = 0 if i == 0 else LATENCY_BOUNDS_MS[i - 1]
            hi = LATENCY_BOUNDS_MS[i] if i < len(LATENCY_BOUNDS_MS) else LATENCY_BOUNDS_MS[-1] * 2
            frac = (target - cum) / c
            return round(lo + (hi - lo) * frac, 1)
        cum += c
    return float(LATENCY_BOUNDS_MS[-1])


def merge(rows: Iterable[dict]) -> dict:
    """Sum the measures of several aggregate rows."""
    out = {"requests": 0, "bot_requests": 0, "failovers": 0, "bytes_sent": 0, "bytes_received": 0,
           "rt_count": 0, "rt_sum": 0, "last_seen": None, "hist": [0] * HIST_LEN}
    for r in rows:
        for k in ("requests", "bot_requests", "failovers", "bytes_sent", "bytes_received", "rt_count", "rt_sum"):
            out[k] += r[k]
        out["hist"] = [a + b for a, b in zip(out["hist"], r["hist"])]
        if r["last_seen"] and (out["last_seen"] is None or r["last_seen"] > out["last_seen"]):
            out["last_seen"] = r["last_seen"]
    return out


def latency_summary(m: dict) -> dict:
    return {
        "avg": round(m["rt_sum"] / m["rt_count"], 1) if m["rt_count"] else None,
        "p50": percentile(m["hist"], 0.50),
        "p95": percentile(m["hist"], 0.95),
        "p99": percentile(m["hist"], 0.99),
    }


def auto_stride(start: Optional[datetime], end: Optional[datetime], now: Optional[datetime] = None) -> timedelta:
    """A chart bucket size giving roughly 24–120 points; whole hours from 2 days up,
    so longer windows can come from the hourly rollup."""
    now = now or datetime.now(timezone.utc)
    span = (end or now) - (start or (now - timedelta(days=30)))
    if span <= timedelta(hours=1):
        return timedelta(minutes=1)
    if span <= timedelta(hours=6):
        return timedelta(minutes=5)
    if span <= timedelta(days=2):
        return timedelta(hours=1)
    if span <= timedelta(days=8):
        return timedelta(hours=3)
    if span <= timedelta(days=31):
        return timedelta(hours=12)
    return timedelta(days=1)
