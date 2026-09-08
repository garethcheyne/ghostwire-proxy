"""IP enrichment service — gathers intelligence about attacker IPs.

Uses multiple free/freemium sources:
- ip-api.com (free, no key needed, 45 req/min)
- Reverse DNS lookup
- AbuseIPDB (optional, requires API key)
"""

import asyncio
import json
import logging
import socket
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, insert

from app.models.honeypot import IpEnrichment, AbuseIPDBBlacklistEntry
from app.models.traffic_log import TrafficLog

logger = logging.getLogger(__name__)

# Cache enrichment for 24 hours before re-fetching
ENRICHMENT_TTL = timedelta(hours=24)

# If a previous AbuseIPDB /check attempt left abuse_score unset (no key was
# configured yet at the time, or the call failed/was rate-limited), don't
# retry it on every single hit - wait at least this long between attempts.
# Without this, one AbuseIPDB failure permanently exempts that IP from the
# 24h cache and it gets re-queried on every future lookup.
ABUSE_CHECK_RETRY_BACKOFF = timedelta(hours=6)

# ip-api.com rate limit: 45 requests per minute
_IP_API_SEMAPHORE = asyncio.Semaphore(5)


async def _lookup_ip_api(ip: str) -> dict:
    """Query ip-api.com for geo/network/ISP data (free, no key)."""
    async with _IP_API_SEMAPHORE:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"http://ip-api.com/json/{ip}",
                    params={
                        "fields": "status,message,country,countryCode,region,regionName,"
                                  "city,zip,lat,lon,timezone,isp,org,as,asname,"
                                  "mobile,proxy,hosting,query"
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        return data
                    logger.warning("ip-api.com lookup failed for %s: %s", ip, data.get("message"))
        except Exception as e:
            logger.warning("ip-api.com request failed for %s: %s", ip, e)
    return {}


async def _reverse_dns(ip: str) -> Optional[str]:
    """Perform reverse DNS lookup."""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: socket.gethostbyaddr(ip))
        return result[0] if result else None
    except (socket.herror, socket.gaierror, OSError):
        return None


async def _lookup_abuseipdb(ip: str, api_key: str) -> dict:
    """Query AbuseIPDB for reputation data (requires API key)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.abuseipdb.com/api/v2/check",
                params={"ipAddress": ip, "maxAgeInDays": "90", "verbose": ""},
                headers={
                    "Key": api_key,
                    "Accept": "application/json",
                },
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                return data
            logger.warning("AbuseIPDB lookup failed for %s: HTTP %d", ip, resp.status_code)
    except Exception as e:
        logger.warning("AbuseIPDB request failed for %s: %s", ip, e)
    return {}


# Minimum time between /blacklist syncs. That endpoint has its own, much
# tighter rate limit than /check (as low as 5 req/day on some plans) - this
# stays well under that even accounting for a manual force-sync or two.
BLACKLIST_SYNC_MIN_INTERVAL = timedelta(hours=20)

# AbuseIPDB's own default/max for a single /blacklist call without a
# higher-tier subscription; asking for more than the plan allows doesn't
# error, it just gets capped, so it's safe to always ask for this many.
BLACKLIST_FETCH_LIMIT = 10000


async def sync_abuseipdb_blacklist(
    db: AsyncSession,
    api_key: str,
    confidence_minimum: int = 75,
    force: bool = False,
) -> dict:
    """Refresh the local AbuseIPDB blacklist cache, at most once every
    BLACKLIST_SYNC_MIN_INTERVAL (unless force=True). One API call regardless
    of how many IPs come back, since /blacklist is rate-limited by request
    count, not by items requested.
    """
    result = await db.execute(select(func.max(AbuseIPDBBlacklistEntry.synced_at)))
    last_synced = result.scalar()
    if not force and last_synced:
        age = datetime.now(timezone.utc) - last_synced
        if age < BLACKLIST_SYNC_MIN_INTERVAL:
            return {"status": "skipped", "reason": "synced recently", "last_synced_at": last_synced}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://api.abuseipdb.com/api/v2/blacklist",
                params={"confidenceMinimum": str(confidence_minimum), "limit": str(BLACKLIST_FETCH_LIMIT)},
                headers={"Key": api_key, "Accept": "application/json"},
            )
            if resp.status_code != 200:
                logger.warning("AbuseIPDB blacklist sync failed: HTTP %d %s", resp.status_code, resp.text[:200])
                return {"status": "failed", "http_status": resp.status_code}
            entries = resp.json().get("data", [])
    except Exception as e:
        logger.warning("AbuseIPDB blacklist sync failed: %s", e)
        return {"status": "failed", "error": str(e)}

    now = datetime.now(timezone.utc)
    rows = [
        {
            "ip_address": item["ipAddress"],
            "abuse_confidence_score": item.get("abuseConfidenceScore", confidence_minimum),
            "country_code": item.get("countryCode"),
            "last_reported_at": (
                datetime.fromisoformat(item["lastReportedAt"].replace("Z", "+00:00"))
                if item.get("lastReportedAt") else None
            ),
            "synced_at": now,
        }
        for item in entries
        if item.get("ipAddress")
    ]

    # Replace wholesale in one transaction - other sessions never see a
    # partial/empty table, just the old set until this commits, then the new one.
    await db.execute(delete(AbuseIPDBBlacklistEntry))
    if rows:
        await db.execute(insert(AbuseIPDBBlacklistEntry.__table__), rows)
    await db.commit()

    logger.info("AbuseIPDB blacklist synced: %d IPs (confidenceMinimum=%d)", len(rows), confidence_minimum)
    return {"status": "synced", "count": len(rows), "synced_at": now}


async def check_local_blacklist(db: AsyncSession, ip: str) -> Optional[AbuseIPDBBlacklistEntry]:
    """Look up an IP in the local AbuseIPDB blacklist cache - free, no API call."""
    result = await db.execute(
        select(AbuseIPDBBlacklistEntry).where(AbuseIPDBBlacklistEntry.ip_address == ip)
    )
    return result.scalar_one_or_none()


async def enrich_ip(
    db: AsyncSession,
    ip: str,
    force: bool = False,
    abuseipdb_key: Optional[str] = None,
) -> IpEnrichment:
    """Enrich an IP address with all available intelligence.

    Returns cached data if available and fresh, or fetches new data.
    """
    # Check for existing enrichment
    result = await db.execute(
        select(IpEnrichment).where(IpEnrichment.ip_address == ip)
    )
    existing = result.scalar_one_or_none()

    if existing and not force:
        age = datetime.now(timezone.utc) - (existing.updated_at or existing.enriched_at)
        # abuse_score can be legitimately None for two very different reasons:
        # (a) no AbuseIPDB key was configured yet when this record was first
        #     enriched - worth catching up on once a key shows up, or
        # (b) a /check attempt was already made and failed (rate-limited,
        #     network error) - retrying on every single hit is what blew
        #     through the daily quota in the first place, so this only
        #     becomes eligible again after a backoff window, same as any
        #     other cached field.
        abuse_worth_retrying = (
            abuseipdb_key and existing.abuse_score is None and age >= ABUSE_CHECK_RETRY_BACKOFF
        )
        if age < ENRICHMENT_TTL and not abuse_worth_retrying:
            return existing

    # Check the free local AbuseIPDB blacklist cache before ever spending a
    # metered /check call - most honeypot-hitting IPs are already known-bad
    # and show up here (confidenceMinimum=75) at zero API cost.
    local_blacklist_hit = await check_local_blacklist(db, ip) if abuseipdb_key else None
    call_abuseipdb_live = bool(abuseipdb_key) and local_blacklist_hit is None

    # Gather data from all sources in parallel
    tasks = [_lookup_ip_api(ip), _reverse_dns(ip)]
    if call_abuseipdb_live:
        tasks.append(_lookup_abuseipdb(ip, abuseipdb_key))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    ip_api_data = results[0] if not isinstance(results[0], Exception) else {}
    rdns = results[1] if not isinstance(results[1], Exception) else None
    abuse_data = {}
    if call_abuseipdb_live and len(results) > 2 and not isinstance(results[2], Exception):
        abuse_data = results[2]
    elif local_blacklist_hit is not None:
        abuse_data = {
            "abuseConfidenceScore": local_blacklist_hit.abuse_confidence_score,
            "totalReports": None,
            "lastReportedAt": (
                local_blacklist_hit.last_reported_at.isoformat()
                if local_blacklist_hit.last_reported_at else None
            ),
            "isTor": None,
        }

    # Build enrichment record
    now = datetime.now(timezone.utc)

    raw_combined = {
        "ip_api": ip_api_data if isinstance(ip_api_data, dict) else {},
        "reverse_dns": rdns,
        "abuseipdb": abuse_data if isinstance(abuse_data, dict) else {},
    }

    enrichment_data = {
        "ip_address": ip,
        "country_code": ip_api_data.get("countryCode"),
        "country_name": ip_api_data.get("country"),
        "city": ip_api_data.get("city"),
        "region": ip_api_data.get("regionName"),
        "latitude": str(ip_api_data.get("lat", "")) if ip_api_data.get("lat") else None,
        "longitude": str(ip_api_data.get("lon", "")) if ip_api_data.get("lon") else None,
        "timezone": ip_api_data.get("timezone"),
        "isp": ip_api_data.get("isp"),
        "org": ip_api_data.get("org"),
        "asn": str(ip_api_data.get("as", "")).split(" ")[0] if ip_api_data.get("as") else None,
        "as_name": ip_api_data.get("asname"),
        "reverse_dns": rdns,
        "is_proxy": ip_api_data.get("proxy"),
        "is_vpn": ip_api_data.get("hosting"),  # ip-api 'hosting' flag indicates datacenter/VPN
        "is_datacenter": ip_api_data.get("hosting"),
        "abuse_score": abuse_data.get("abuseConfidenceScore"),
        "abuse_reports": abuse_data.get("totalReports"),
        "abuse_last_reported": (
            datetime.fromisoformat(abuse_data["lastReportedAt"].replace("Z", "+00:00"))
            if abuse_data.get("lastReportedAt")
            else None
        ),
        "is_tor": abuse_data.get("isTor"),
        "is_crawler": None,  # Could be populated by user-agent analysis
        "raw_data": json.dumps(raw_combined, default=str),
        "enriched_at": now,
        "updated_at": now,
    }

    if existing:
        for field, value in enrichment_data.items():
            if field != "ip_address":
                setattr(existing, field, value)
        await db.commit()
        await db.refresh(existing)
        return existing
    else:
        enrichment = IpEnrichment(**enrichment_data)
        db.add(enrichment)
        await db.commit()
        await db.refresh(enrichment)
        return enrichment


async def get_enrichment(db: AsyncSession, ip: str) -> Optional[IpEnrichment]:
    """Get existing enrichment data for an IP, or None."""
    result = await db.execute(
        select(IpEnrichment).where(IpEnrichment.ip_address == ip)
    )
    return result.scalar_one_or_none()


async def backfill_enrichment(db: AsyncSession, batch_size: int = 40) -> dict:
    """Enrich IPs from traffic logs that don't yet have enrichment records.

    Processes one batch at a time to respect ip-api.com rate limits (45 req/min).
    Returns stats about the backfill run.
    """
    # Find unique IPs in traffic_logs that have no IpEnrichment record
    subq = select(IpEnrichment.ip_address)
    query = (
        select(func.distinct(TrafficLog.client_ip))
        .where(
            TrafficLog.client_ip.isnot(None),
            ~TrafficLog.client_ip.in_(subq),
        )
        .limit(batch_size)
    )
    result = await db.execute(query)
    ips = [row[0] for row in result.all()]

    if not ips:
        return {"enriched": 0, "remaining": 0, "status": "complete"}

    # Get optional AbuseIPDB key
    from app.models.setting import Setting
    abuseipdb_key = None
    setting_result = await db.execute(
        select(Setting).where(Setting.key == "abuseipdb_api_key")
    )
    setting = setting_result.scalar_one_or_none()
    if setting and setting.value:
        abuseipdb_key = setting.value

    enriched = 0
    for ip in ips:
        try:
            await enrich_ip(db, ip, abuseipdb_key=abuseipdb_key)
            enriched += 1
            # Pace requests: ~40 per minute to stay under ip-api.com's 45/min
            await asyncio.sleep(1.5)
        except Exception as e:
            logger.warning("Backfill enrichment failed for %s: %s", ip, e)

    # Count how many are still remaining
    remaining_result = await db.execute(
        select(func.count(func.distinct(TrafficLog.client_ip)))
        .where(
            TrafficLog.client_ip.isnot(None),
            ~TrafficLog.client_ip.in_(subq),
        )
    )
    remaining = remaining_result.scalar() or 0

    return {
        "enriched": enriched,
        "remaining": remaining,
        "status": "in_progress" if remaining > 0 else "complete",
    }


# Maximum age before stale enrichment records are deleted
ENRICHMENT_MAX_AGE = timedelta(days=7)


async def cleanup_stale_enrichments(db: AsyncSession) -> int:
    """Delete enrichment records older than ENRICHMENT_MAX_AGE that are no longer
    referenced by any traffic log or threat actor. Returns count of deleted rows."""
    from sqlalchemy import delete

    cutoff = datetime.now(timezone.utc) - ENRICHMENT_MAX_AGE
    result = await db.execute(
        delete(IpEnrichment).where(IpEnrichment.updated_at < cutoff)
    )
    await db.commit()
    deleted = result.rowcount
    if deleted:
        logger.info("Cleaned up %d stale IP enrichment records", deleted)
    return deleted
