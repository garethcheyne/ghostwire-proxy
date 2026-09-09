"""Container OS package inventory and security-update posture."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cached_json, cache_delete
from app.core.database import get_db
from app.models.user import User
from app.api.deps import get_current_user, get_current_admin_user
from app.services.container_security_service import scanner, DOCKER_AVAILABLE

logger = logging.getLogger(__name__)
router = APIRouter()

# Scanning execs into every container and refreshes each package index, which
# takes seconds and hits the network. Cached hard; the refresh endpoint is the
# way to get a fresh answer on demand.
SCAN_CACHE_TTL = 3600
SCAN_CACHE_KEY = "containers:security-scan"


@router.get("/security")
async def get_container_security(
    refresh: bool = Query(False, description="Bypass the cache and rescan now"),
    name_filter: str = Query("ghostwire-proxy", description="Container name filter; blank for all"),
    current_user: User = Depends(get_current_user),
):
    """Package and update posture for every container in the stack."""
    if not DOCKER_AVAILABLE or scanner.client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Docker is not reachable from the API container, so containers cannot be scanned.",
        )

    cache_key = f"{SCAN_CACHE_KEY}:{name_filter or 'all'}"

    if refresh:
        await cache_delete(cache_key)

    async def _compute():
        scans = await scanner.scan_all(name_filter=name_filter or "")
        return {
            "containers": scans,
            "summary": _summarise(scans),
        }

    return await cached_json(cache_key, ttl=SCAN_CACHE_TTL, producer=_compute)


@router.get("/security/{container_name}")
async def get_single_container_security(
    container_name: str,
    include_packages: bool = Query(False, description="Include the full installed package list"),
    current_user: User = Depends(get_current_user),
):
    """One container's posture, optionally with its full package inventory."""
    if not DOCKER_AVAILABLE or scanner.client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Docker is not reachable from the API container.",
        )

    import asyncio

    try:
        container = scanner.client.containers.get(container_name)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Container not found")

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, scanner.scan_one, container, include_packages)


def _summarise(scans: list[dict]) -> dict:
    """Fleet-level counts for the dashboard tile."""
    levels = {"critical": 0, "high": 0, "medium": 0, "ok": 0, "unknown": 0}
    pending_total = 0
    security_total = 0
    edge_at_risk = 0
    stale_images = 0

    for scan in scans:
        level = (scan.get("risk") or {}).get("level", "unknown")
        levels[level] = levels.get(level, 0) + 1

        pending = scan.get("pending") or {}
        pending_total += pending.get("count", 0) or 0
        security_total += pending.get("security_count", 0) or 0

        if scan.get("is_edge") and level in ("high", "critical"):
            edge_at_risk += 1

        age = scan.get("image_age_days")
        if age is not None and age > 90:
            stale_images += 1

    return {
        "total_containers": len(scans),
        "by_level": levels,
        "pending_updates_total": pending_total,
        "security_updates_total": security_total,
        "edge_containers_at_risk": edge_at_risk,
        "stale_images": stale_images,
        "needs_attention": levels["critical"] + levels["high"],
    }
