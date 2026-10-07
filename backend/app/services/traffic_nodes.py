"""Shared lookups and shaping for the Traffic page and host reports: backend
(upstream) facts, per-node breakdowns, chart buckets."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.known_ip import KnownIp
from app.models.proxy_host import ProxyHost, UpstreamServer
from app.services import traffic_query as tq


def empty_meta() -> dict:
    return {"label": None, "configured_for": [], "health": []}


def host_part(backend: Optional[str]) -> str:
    backend = backend or ""
    return tq.host_of(backend) if tq.BACKEND_WITH_PORT.match(backend) else backend


async def host_names(db: AsyncSession, ids: list[str]) -> dict[str, str]:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    rows = (await db.execute(select(ProxyHost.id, ProxyHost.domain_names).where(ProxyHost.id.in_(ids)))).all()
    return {r[0]: (r[1][0] if r[1] else "Unknown") for r in rows}


async def known_labels(db: AsyncSession, ips: list[str]) -> dict[str, str]:
    ips = [i for i in ips if i]
    if not ips:
        return {}
    rows = (await db.execute(select(KnownIp.ip_address, KnownIp.label).where(KnownIp.ip_address.in_(ips)))).all()
    return {r[0]: r[1] for r in rows}


async def backend_meta(db: AsyncSession, backends: list[str]) -> dict[str, dict]:
    """Per backend host: known-IP label, the proxy hosts whose forward host or
    upstream servers point at it, and per-server health when the load-balancing
    fields exist."""
    hosts = {host_part(b) for b in backends if b}
    if not hosts:
        return {}
    out: dict[str, dict] = {h: empty_meta() for h in hosts}
    for ip, label in (await known_labels(db, list(hosts))).items():
        out[ip]["label"] = label
    bare = {h.strip("[]"): h for h in hosts}
    rows = (await db.execute(
        select(ProxyHost.id, ProxyHost.domain_names, ProxyHost.forward_host, ProxyHost.forward_port)
        .where(ProxyHost.forward_host.in_(list(bare)))
    )).all()
    for pid, names, fh, fp in rows:
        out[bare[fh]]["configured_for"].append(
            {"id": pid, "name": names[0] if names else "Unknown", "port": fp, "via": "forward_host"})
    servers = (await db.execute(
        select(UpstreamServer, ProxyHost.domain_names)
        .join(ProxyHost, ProxyHost.id == UpstreamServer.proxy_host_id)
        .where(UpstreamServer.host.in_(list(bare)))
    )).all()
    for srv, names in servers:
        key = bare[srv.host]
        out[key]["configured_for"].append(
            {"id": srv.proxy_host_id, "name": names[0] if names else "Unknown", "port": srv.port, "via": "upstream"})
        if hasattr(srv, "last_status"):  # load-balancing health fields, when present
            out[key]["health"].append({
                "port": srv.port, "status": getattr(srv, "last_status", None),
                "checked_at": getattr(srv, "last_check_at", None),
                "latency_ms": getattr(srv, "last_latency_ms", None),
                "error": getattr(srv, "last_error", None),
                "enabled": srv.enabled,
                "down": bool(getattr(srv, "down", False) or getattr(srv, "auto_down", False)),
                "backup": bool(getattr(srv, "backup", False)),
                "host_name": names[0] if names else None,
            })
    return out


def buckets(start: Optional[datetime], end: datetime, stride: timedelta, present: dict) -> list[datetime]:
    """Every bucket in the window (so the chart shows zeros, not gaps), or only the
    ones with data when the window is open-ended."""
    if start is None:
        return sorted(present)
    first = tq.ORIGIN + ((start - tq.ORIGIN) // stride) * stride
    out, b = [], first
    while b < end and len(out) < 2000:
        out.append(b)
        b += stride
    return out


MAX_SERIES_NODES = 8


def build_nodes_summary(rows, series_rows, pairs, meta, *, start, end, stride) -> dict:
    """Shape per-node aggregates for the API and the host report."""
    by_node: dict[str, list[dict]] = {}
    for r in rows:
        by_node.setdefault(r["upstream"], []).append(r)
    total = sum(r["requests"] for r in rows)
    fell_from: dict[str, int] = {}
    for pr in pairs:
        fell_from[pr["from"]] = fell_from.get(pr["from"], 0) + pr["requests"]
    nodes = []
    for node, rs in by_node.items():
        m = tq.merge(rs)
        e4 = sum(r["requests"] for r in rs if r["status_class"] == 4)
        e5 = sum(r["requests"] for r in rs if r["status_class"] == 5)
        lat = tq.latency_summary(m)
        host = host_part(node)
        port = node.rsplit(":", 1)[1] if tq.BACKEND_WITH_PORT.match(node or "") else None
        info = meta.get(host, empty_meta())
        nodes.append({
            "node": node,  # '' = answered by the proxy itself
            "label": info["label"],
            "requests": m["requests"],
            "share": round(m["requests"] / total * 100, 2) if total else 0.0,
            "errors_4xx": e4, "errors_5xx": e5,
            "error_rate": round((e4 + e5) / m["requests"] * 100, 2) if m["requests"] else 0.0,
            "server_error_rate": round(e5 / m["requests"] * 100, 2) if m["requests"] else 0.0,
            "p50": lat["p50"], "p95": lat["p95"], "avg": lat["avg"],
            "bytes_sent": m["bytes_sent"], "bytes_received": m["bytes_received"],
            # Requests this node answered after another node failed them …
            "failovers_in": m["failovers"],
            # … and requests this node failed that another then answered.
            "failovers_out": fell_from.get(node, 0),
            "last_seen": m["last_seen"],
            "health": [h for h in info["health"] if port is None or str(h["port"]) == port],
        })
    nodes.sort(key=lambda n: -n["requests"])
    shown = [n["node"] for n in nodes[:MAX_SERIES_NODES]]
    per_bucket: dict = {}
    for r in series_rows:
        key = r["upstream"] if r["upstream"] in shown else "other"
        bucket = per_bucket.setdefault(r["bucket"], {})
        bucket[key] = bucket.get(key, 0) + r["requests"]
    points = [
        {"t": b.isoformat(), "values": per_bucket.get(b, {})}
        for b in buckets(start, end, stride, per_bucket)
    ]
    return {
        "total_requests": total,
        "nodes": nodes,
        "series_nodes": shown + (["other"] if len(nodes) > MAX_SERIES_NODES else []),
        "stride_seconds": int(stride.total_seconds()),
        "timeseries": points,
        "failovers": {"total": sum(n["failovers_in"] for n in nodes), "pairs": pairs},
    }




async def node_summary(db: AsyncSession, f: tq.TrafficFilters, *, now: datetime) -> dict:
    """Per-node figures for the filters (see build_nodes_summary)."""
    stride = tq.auto_stride(f.start, f.end, now)
    watermark = await tq.rolled_until(db)
    rows = await tq.aggregate(db, f, ["upstream", "status_class"], watermark=watermark)
    series_rows = await tq.aggregate(db, f, ["upstream"], stride=stride, watermark=watermark)
    pairs = await tq.failover_pairs(db, f)
    meta = await backend_meta(db, [r["upstream"] for r in rows])
    return build_nodes_summary(rows, series_rows, pairs, meta, start=f.start, end=f.end or now, stride=stride)
