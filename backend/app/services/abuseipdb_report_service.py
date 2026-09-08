"""Reports confirmed attackers back to AbuseIPDB.

Ghostwire already has strong signal for "this IP is genuinely malicious" -
ThreatActor rows that escalated past monitoring (temp_blocked and worse) plus
the ThreatEvent categories that got them there. This submits that intelligence
back to AbuseIPDB via /bulk-report (its own, separate daily quota from
/check - doesn't compete with the enrichment lookups in enrichment_service.py),
once a day, so it strengthens both Ghostwire's own future lookups and the
wider community's.

Gated on the `abuseipdb_auto_report_enabled` setting (default off - opt in
from Settings, same place the API key lives). Trusted IPs are always excluded
so testing from an admin's own trusted IP never gets reported.
"""
import csv
import io
import ipaddress
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.waf import ThreatActor, ThreatEvent

logger = logging.getLogger(__name__)

# Only actors that escalated at least this far are reported - "monitored"
# and "warned" are too weak a signal to submit to a shared public database.
REPORTABLE_STATUSES = ("temp_blocked", "perm_blocked", "firewall_banned")

# Only consider actors active within this window, so we don't resurrect and
# report long-dormant historical actors with a stale "now" timestamp.
ACTIVITY_WINDOW = timedelta(hours=24)

# Minimum time between report runs (bulk-report shares AbuseIPDB's report
# quota, separate from /check, but there's no reason to run more than daily).
REPORT_SYNC_MIN_INTERVAL = timedelta(hours=20)

BULK_REPORT_URL = "https://api.abuseipdb.com/api/v2/bulk-report"

# Internal category -> AbuseIPDB category IDs (see abuseipdb.com/categories).
CATEGORY_MAP: dict[str, list[int]] = {
    "sqli": [16, 21],             # SQL Injection, Web App Attack
    "xss": [21],                  # Web App Attack
    "path_traversal": [21],       # Web App Attack
    "rce": [15, 21],              # Hacking, Web App Attack
    "scanner": [14, 21],          # Port Scan, Web App Attack
    "honeypot": [15, 21],         # Hacking, Web App Attack
}
DEFAULT_CATEGORIES = [15]  # Hacking - fallback for an unmapped/unknown category


async def _get_trusted_networks(db: AsyncSession) -> list:
    """Parse the trusted_ips setting into ip_network objects for membership checks."""
    from app.models.setting import Setting

    result = await db.execute(select(Setting).where(Setting.key == "trusted_ips"))
    setting = result.scalar_one_or_none()
    if not setting or not setting.value:
        return []

    try:
        raw = json.loads(setting.value)
    except (json.JSONDecodeError, TypeError):
        return []

    networks = []
    for entry in raw:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning("trusted_ips: skipping unparseable entry %r", entry)
    return networks


def _is_trusted(ip: str, trusted_networks: list) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in trusted_networks)


def _categories_for(categories_seen: set[str]) -> str:
    ids: set[int] = set()
    for cat in categories_seen:
        ids.update(CATEGORY_MAP.get(cat, DEFAULT_CATEGORIES))
    if not ids:
        ids.update(DEFAULT_CATEGORIES)
    return ",".join(str(i) for i in sorted(ids))


def _build_comment(categories_seen: set[str], event_count: int, sample_uri: Optional[str], sample_method: Optional[str]) -> str:
    """PII-stripped summary - category/count/path only, never raw headers,
    cookies, or User-Agent strings (per AbuseIPDB's PII guidance)."""
    cats = ", ".join(sorted(categories_seen)) if categories_seen else "suspicious activity"
    comment = f"Ghostwire Proxy: {event_count} {cats} event(s) in the last 24h detected by WAF/honeypot."
    if sample_method and sample_uri:
        # Strip query string - it can carry incidental PII (emails, tokens) in the payload itself
        path = sample_uri.split("?", 1)[0]
        comment += f" Example: {sample_method} {path}"
    return comment[:1024]


async def submit_bulk_reports(db: AsyncSession, api_key: str, force: bool = False) -> dict:
    """Find newly-escalated, still-active threat actors and report them to
    AbuseIPDB in a single bulk-report call. Safe to call repeatedly - no-ops
    if run within REPORT_SYNC_MIN_INTERVAL unless force=True.
    """
    from sqlalchemy import func

    result = await db.execute(select(func.max(ThreatActor.abuseipdb_reported_at)))
    last_run = result.scalar()
    if not force and last_run and (datetime.now(timezone.utc) - last_run) < REPORT_SYNC_MIN_INTERVAL:
        return {"status": "skipped", "reason": "reported recently", "last_run_at": last_run}

    cutoff = datetime.now(timezone.utc) - ACTIVITY_WINDOW
    result = await db.execute(
        select(ThreatActor).where(
            ThreatActor.current_status.in_(REPORTABLE_STATUSES),
            ThreatActor.last_seen.isnot(None),
            ThreatActor.last_seen >= cutoff,
        )
    )
    candidates = [
        a for a in result.scalars().all()
        if a.abuseipdb_reported_at is None or (a.last_seen and a.abuseipdb_reported_at < a.last_seen)
    ]

    if not candidates:
        return {"status": "complete", "reported": 0, "skipped_trusted": 0}

    trusted_networks = await _get_trusted_networks(db)
    reportable = []
    skipped_trusted = 0
    for actor in candidates:
        if _is_trusted(actor.ip_address, trusted_networks):
            skipped_trusted += 1
            continue
        reportable.append(actor)

    if not reportable:
        return {"status": "complete", "reported": 0, "skipped_trusted": skipped_trusted}

    # Build one CSV row per actor, summarizing their recent ThreatEvents
    rows = []
    for actor in reportable:
        event_result = await db.execute(
            select(ThreatEvent)
            .where(ThreatEvent.client_ip == actor.ip_address, ThreatEvent.timestamp >= cutoff)
            .order_by(ThreatEvent.timestamp.desc())
        )
        events = event_result.scalars().all()
        categories_seen = {e.category for e in events if e.category}
        latest = events[0] if events else None

        rows.append({
            "ip": actor.ip_address,
            "categories": _categories_for(categories_seen),
            "report_date": (actor.last_seen or datetime.now(timezone.utc)).isoformat(),
            "comment": _build_comment(
                categories_seen, len(events) or actor.total_events or 1,
                latest.request_uri if latest else None,
                latest.request_method if latest else None,
            ),
        })

    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(["IP", "Categories", "ReportDate", "Comment"])
    for row in rows:
        writer.writerow([row["ip"], row["categories"], row["report_date"], row["comment"]])

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                BULK_REPORT_URL,
                headers={"Key": api_key, "Accept": "application/json"},
                files={"csv": ("report.csv", csv_buf.getvalue().encode(), "text/csv")},
            )
    except Exception as e:
        logger.warning("AbuseIPDB bulk-report failed: %s", e)
        return {"status": "failed", "error": str(e)}

    if resp.status_code != 200:
        logger.warning("AbuseIPDB bulk-report failed: HTTP %d %s", resp.status_code, resp.text[:300])
        return {"status": "failed", "http_status": resp.status_code}

    body = resp.json().get("data", {})
    rejected = body.get("invalidReports", [])
    # `input` is the raw CSV field value that caused the row to fail (an IP
    # for "Duplicate IP"/"Invalid IP", the row's IP either way in practice).
    rejected_ips = {r.get("input") for r in rejected} if rejected else set()

    now = datetime.now(timezone.utc)
    reported_count = 0
    for actor in reportable:
        if actor.ip_address in rejected_ips:
            continue
        actor.abuseipdb_reported_at = now
        reported_count += 1
    await db.commit()

    if rejected:
        logger.warning("AbuseIPDB bulk-report: %d entries rejected: %s",
                        len(rejected), [f"{r.get('input')} ({r.get('error')})" for r in rejected][:10])

    logger.info(
        "AbuseIPDB bulk-report: submitted %d IPs (%d accepted, %d rejected, %d skipped as trusted)",
        len(rows), reported_count, len(rejected), skipped_trusted,
    )
    return {
        "status": "reported",
        "submitted": len(rows),
        "accepted": reported_count,
        "rejected": len(rejected),
        "skipped_trusted": skipped_trusted,
    }
