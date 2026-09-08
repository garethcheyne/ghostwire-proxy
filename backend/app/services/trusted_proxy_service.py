"""
Keeps the CDN edge ranges that nginx is allowed to take a real-client-IP header
from.

Why this exists: `set_real_ip_from` is the only thing standing between "we know
the visitor's IP" and "any visitor can claim to be any IP". Those ranges are
published by each provider and do change, so a hardcoded list silently rots —
and a rotted list means either the CDN's own edge IP gets logged, rate-limited
and threat-scored as if it were the visitor, or a range we no longer should
trust still is.
"""
import json
import logging
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setting import Setting

logger = logging.getLogger(__name__)

SETTING_KEY = "trusted_proxy_ranges"
FETCH_TIMEOUT = 20.0

CLOUDFLARE_V4_URL = "https://www.cloudflare.com/ips-v4"
CLOUDFLARE_V6_URL = "https://www.cloudflare.com/ips-v6"
# Imperva publishes its edge ranges from an unauthenticated POST endpoint.
IMPERVA_URL = "https://my.imperva.com/api/integration/v1/ips"

# Used until the first successful fetch. Same Cloudflare snapshot that
# proxy/nginx.conf carries, so behaviour doesn't regress if the network is
# unavailable. Imperva has no snapshot: publishing a guessed range would tell
# nginx to trust a network we haven't verified, which is worse than not
# supporting it yet.
FALLBACK_RANGES: dict[str, list[str]] = {
    "cloudflare": [
        "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
        "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
        "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
        "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
        "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32",
        "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
    ],
    "imperva": [],
}

_CIDR_CHARS = set("0123456789abcdefABCDEF.:/")


def _looks_like_cidr(value: str) -> bool:
    """Cheap sanity check — these strings end up in an nginx directive."""
    value = value.strip()
    if not value or "/" not in value or len(value) > 64:
        return False
    return set(value) <= _CIDR_CHARS


def _clean(values) -> list[str]:
    out = []
    for v in values or []:
        v = str(v).strip()
        if _looks_like_cidr(v) and v not in out:
            out.append(v)
    return out


async def _fetch_cloudflare(client: httpx.AsyncClient) -> list[str]:
    ranges: list[str] = []
    for url in (CLOUDFLARE_V4_URL, CLOUDFLARE_V6_URL):
        resp = await client.get(url)
        resp.raise_for_status()
        ranges.extend(resp.text.split("\n"))
    return _clean(ranges)


async def _fetch_imperva(client: httpx.AsyncClient) -> list[str]:
    resp = await client.post(IMPERVA_URL)
    resp.raise_for_status()
    payload = resp.json()
    return _clean(payload.get("ipRanges", []) + payload.get("ipv6Ranges", []))


async def refresh_ranges(db: AsyncSession) -> dict[str, int]:
    """Fetch each provider's published ranges and cache them."""
    current = await get_ranges(db)
    updated = dict(current)

    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, follow_redirects=True) as client:
        for provider, fetch in (("cloudflare", _fetch_cloudflare), ("imperva", _fetch_imperva)):
            try:
                fetched = await fetch(client)
                if fetched:
                    updated[provider] = fetched
                else:
                    # Never let an empty response widen or clear the trust list.
                    logger.warning(f"{provider} returned no usable ranges; keeping cached set")
            except Exception as e:
                logger.warning(f"Could not refresh {provider} ranges: {e}")

    result = await db.execute(select(Setting).where(Setting.key == SETTING_KEY))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = Setting(
            key=SETTING_KEY,
            description="Published CDN edge ranges trusted for real-client-IP headers",
        )
        db.add(setting)
    setting.value = json.dumps(updated)
    await db.commit()

    counts = {k: len(v) for k, v in updated.items()}
    logger.info(f"Trusted proxy ranges refreshed: {counts}")
    return counts


async def get_ranges(db: AsyncSession) -> dict[str, list[str]]:
    """Cached ranges per provider, falling back to the bundled snapshot."""
    ranges = {k: list(v) for k, v in FALLBACK_RANGES.items()}
    try:
        result = await db.execute(select(Setting).where(Setting.key == SETTING_KEY))
        setting = result.scalar_one_or_none()
        if setting and setting.value:
            stored = json.loads(setting.value)
            for provider, values in stored.items():
                cleaned = _clean(values)
                if cleaned:
                    ranges[provider] = cleaned
    except Exception as e:
        logger.warning(f"Could not read cached trusted proxy ranges: {e}")
    return ranges
