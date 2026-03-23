"""Security presets API — browse and apply best-practice rule templates."""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.utils import get_client_ip
from app.models.user import User
from app.api.deps import get_current_user
from app.services.preset_service import (
    list_presets, get_preset, apply_preset,
    get_applied_presets, remove_preset, reapply_preset,
)

router = APIRouter()


@router.get("")
async def get_presets(
    category: Optional[str] = Query(None, description="Filter by category: waf, geoip, rate_limit, threat_response"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all available security presets with applied status."""
    presets = list_presets(category=category)
    applied = await get_applied_presets(db)

    for preset in presets:
        preset["applied"] = preset["id"] in applied

    return presets


@router.get("/{preset_id}")
async def get_preset_detail(
    preset_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get full preset details including all rules."""
    preset = get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return preset


@router.post("/{preset_id}/apply")
async def apply_preset_route(
    preset_id: str,
    request: Request,
    proxy_host_id: Optional[str] = Query(None, description="Apply GeoIP/rate-limit rules to a specific proxy host"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply a preset — creates rules in the database.

    Presets are additive: applying a preset never removes existing rules.
    """
    try:
        result = await apply_preset(
            preset_id=preset_id,
            db=db,
            user_id=current_user.id,
            proxy_host_id=proxy_host_id,
            client_ip=get_client_ip(request),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{preset_id}/remove")
async def remove_preset_route(
    preset_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove all rules created by a preset."""
    try:
        result = await remove_preset(
            preset_id=preset_id,
            db=db,
            user_id=current_user.id,
            client_ip=get_client_ip(request),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{preset_id}/reapply")
async def reapply_preset_route(
    preset_id: str,
    request: Request,
    proxy_host_id: Optional[str] = Query(None, description="Apply GeoIP/rate-limit rules to a specific proxy host"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-apply a preset — removes existing rules then re-creates from the latest JSON file."""
    try:
        result = await reapply_preset(
            preset_id=preset_id,
            db=db,
            user_id=current_user.id,
            proxy_host_id=proxy_host_id,
            client_ip=get_client_ip(request),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
