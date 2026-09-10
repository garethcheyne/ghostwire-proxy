"""Container OS package inventory and security-update posture."""
import logging
from typing import Optional

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


# ── Automatic OS package updates ────────────────────────────────────────────

AUTO_UPDATE_SETTINGS = {
    "container_auto_update_enabled": "Apply OS package updates inside containers on a schedule",
    "container_auto_update_cron": "Cron expression for the automatic container update run",
    "container_auto_update_security_only": "Restrict automatic updates to security suites where the package manager supports it",
    "container_auto_update_exclude": "Comma-separated container names never updated in place",
}

DEFAULT_UPDATE_CRON = "0 4 * * 0"  # Sundays 04:00 UTC


async def _get_setting(db: AsyncSession, key: str) -> Optional[str]:
    from app.models.setting import Setting
    from sqlalchemy import select

    row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    return row.value if row else None


async def _set_setting(db: AsyncSession, key: str, value: str) -> None:
    from app.models.setting import Setting
    from sqlalchemy import select

    row = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value, description=AUTO_UPDATE_SETTINGS.get(key)))
    await db.commit()


def _truthy(value: Optional[str]) -> bool:
    return bool(value) and str(value).strip().lower() in ("true", "1", "yes", "on")


async def get_auto_update_policy(db: AsyncSession) -> dict:
    from app.services.container_security_service import DEFAULT_EXCLUDED

    raw_exclude = await _get_setting(db, "container_auto_update_exclude")
    user_excluded = [n.strip() for n in (raw_exclude or "").split(",") if n.strip()]

    return {
        "enabled": _truthy(await _get_setting(db, "container_auto_update_enabled")),
        "cron": await _get_setting(db, "container_auto_update_cron") or DEFAULT_UPDATE_CRON,
        # Security-only unless explicitly turned off: a routine patch run should
        # not drag in unrelated version churn on a proxy that is serving.
        "security_only": _truthy(
            await _get_setting(db, "container_auto_update_security_only") or "true"
        ),
        "excluded": user_excluded,
        "always_excluded": list(DEFAULT_EXCLUDED),
    }


@router.get("/auto-update")
async def read_auto_update_policy(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    policy = await get_auto_update_policy(db)
    policy["last_run"] = await _get_setting(db, "container_auto_update_last_run")
    policy["last_result"] = await _get_setting(db, "container_auto_update_last_result")
    return policy


@router.put("/auto-update")
async def write_auto_update_policy(
    payload: dict,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    from croniter import croniter

    if "cron" in payload and payload["cron"]:
        try:
            croniter(str(payload["cron"]))
        except (ValueError, KeyError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Not a valid cron expression: {payload['cron']}",
            )
        await _set_setting(db, "container_auto_update_cron", str(payload["cron"]))

    if "enabled" in payload:
        await _set_setting(db, "container_auto_update_enabled", "true" if payload["enabled"] else "false")
    if "security_only" in payload:
        await _set_setting(
            db, "container_auto_update_security_only", "true" if payload["security_only"] else "false"
        )
    if "excluded" in payload:
        names = payload["excluded"]
        if isinstance(names, list):
            names = ",".join(str(n).strip() for n in names if str(n).strip())
        await _set_setting(db, "container_auto_update_exclude", str(names or ""))

    return await get_auto_update_policy(db)


@router.post("/auto-update/run")
async def run_auto_update_now(
    payload: dict | None = None,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply OS package updates immediately.

    Pass {"container": "<name>"} for one container, or omit it for the whole
    stack. Runs inline rather than in the background so the caller sees the real
    outcome, including which packages moved.
    """
    from app.services.container_security_service import (
        apply_updates, apply_updates_all, DOCKER_AVAILABLE, scanner,
    )

    if not DOCKER_AVAILABLE or scanner.client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Docker is not reachable from the API container.",
        )

    payload = payload or {}
    policy = await get_auto_update_policy(db)
    excluded = set(policy["excluded"]) | set(policy["always_excluded"])
    security_only = bool(payload.get("security_only", policy["security_only"]))

    name = payload.get("container")
    if name:
        results = [await apply_updates(str(name), security_only, excluded)]
    else:
        results = await apply_updates_all(security_only=security_only, excluded=excluded)

    # The scan is now stale for every container touched.
    await cache_delete(f"{SCAN_CACHE_KEY}:ghostwire-proxy")

    upgraded = sum(r.get("upgraded", 0) or 0 for r in results)
    failed = [r["container"] for r in results if r.get("error") and not r.get("skipped")]
    return {"results": results, "packages_upgraded": upgraded, "failed": failed}
