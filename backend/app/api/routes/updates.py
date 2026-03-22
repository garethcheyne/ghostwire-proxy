"""Update management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.models.user import User
from app.api.deps import get_current_user
from app.services.update_service import update_service

router = APIRouter()


# ============================================================================
# SCHEMAS
# ============================================================================

class AppVersionInfo(BaseModel):
    """Information about a single app version/release."""
    version: str
    name: Optional[str] = None
    published_at: Optional[str] = None
    changelog: Optional[str] = None
    html_url: Optional[str] = None
    prerelease: bool = False


class CheckAppUpdatesResponse(BaseModel):
    """Response for app update check."""
    current_version: str
    latest_version: Optional[str] = None
    update_available: bool
    releases: List[AppVersionInfo]
    error: Optional[str] = None


class BaseImageInfo(BaseModel):
    """Information about a container's base image."""
    container: str
    image: str
    update_available: bool
    current_digest: Optional[str] = None
    latest_digest: Optional[str] = None
    error: Optional[str] = None


class StartAppUpdateRequest(BaseModel):
    """Request to start an app update."""
    target_version: str = Field(..., description="Target version to update to")


class StartBaseImageUpdateRequest(BaseModel):
    """Request to start a base image update."""
    container_name: str = Field(
        ...,
        description="Container to update: api, ui, nginx, postgres, redis"
    )


class UpdateStatusResponse(BaseModel):
    """Response for update status."""
    id: str
    update_type: str
    from_version: Optional[str] = None
    to_version: Optional[str] = None
    container_name: Optional[str] = None
    status: str
    progress_percent: int
    progress_message: Optional[str] = None
    error_message: Optional[str] = None
    can_rollback: bool
    rollback_performed: bool = False
    backup_id: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UpdateSettingsResponse(BaseModel):
    """Response for update settings."""
    auto_check_enabled: bool
    check_interval_hours: int
    notify_app_updates: bool
    notify_security_updates: bool
    notify_base_image_updates: bool
    auto_update_security: bool
    update_channel: str
    github_repo: str

    class Config:
        from_attributes = True


class UpdateSettingsUpdate(BaseModel):
    """Request to update settings."""
    auto_check_enabled: Optional[bool] = None
    check_interval_hours: Optional[int] = Field(None, ge=1, le=168)
    notify_app_updates: Optional[bool] = None
    notify_security_updates: Optional[bool] = None
    notify_base_image_updates: Optional[bool] = None
    auto_update_security: Optional[bool] = None
    update_channel: Optional[str] = Field(None, pattern="^(stable|beta|edge)$")
    github_repo: Optional[str] = None


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/check/app", response_model=CheckAppUpdatesResponse)
async def check_app_updates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Check for available application updates.

    Queries GitHub releases and returns available versions.
    """
    result = await update_service.check_for_app_updates(db)
    return CheckAppUpdatesResponse(**result)


@router.get("/check/base-images", response_model=List[BaseImageInfo])
async def check_base_image_updates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Check for available base image updates.

    Queries Docker registries for new image digests.
    """
    results = await update_service.check_for_base_image_updates(db)
    return [BaseImageInfo(**r) for r in results]


@router.post("/app", response_model=UpdateStatusResponse)
async def start_app_update(
    request_body: StartAppUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start an application update.

    This triggers the updater sidecar to:
    1. Create a pre-update backup
    2. Pull the specified version from git
    3. Rebuild container images
    4. Run database migrations
    5. Restart containers in order
    6. Verify health checks
    """
    try:
        update = await update_service.request_app_update(
            db=db,
            target_version=request_body.target_version,
            user_id=current_user.id,
        )
        return UpdateStatusResponse.model_validate(update)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/base-image", response_model=UpdateStatusResponse)
async def start_base_image_update(
    request_body: StartBaseImageUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start a base image update for a specific container.

    Updates the base image (Alpine, Python, Node.js, etc.)
    for the specified container. This pulls the latest version
    of the base image and rebuilds the container.
    """
    try:
        update = await update_service.request_base_image_update(
            db=db,
            container_name=request_body.container_name,
            user_id=current_user.id,
        )
        return UpdateStatusResponse.model_validate(update)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{update_id}", response_model=UpdateStatusResponse)
async def get_update_status(
    update_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the current status of an update operation.

    Polls both Redis (for real-time status) and database.
    """
    update = await update_service.get_update_status(db, update_id)
    if not update:
        raise HTTPException(status_code=404, detail="Update not found")

    return UpdateStatusResponse.model_validate(update)


@router.get("/history", response_model=List[UpdateStatusResponse])
async def get_update_history(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get update history.

    Returns the most recent updates, newest first.
    """
    updates = await update_service.get_update_history(db, limit=limit)
    return [UpdateStatusResponse.model_validate(u) for u in updates]


@router.post("/rollback/{update_id}", response_model=UpdateStatusResponse)
async def rollback_update(
    update_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Rollback a completed update.

    Restores from the pre-update backup and reverts
    to the previous version. Only works for updates
    that have a backup and haven't been rolled back yet.
    """
    try:
        rollback = await update_service.request_rollback(
            db=db,
            update_id=update_id,
            user_id=current_user.id,
        )
        return UpdateStatusResponse.model_validate(rollback)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings", response_model=UpdateSettingsResponse)
async def get_update_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get update settings."""
    settings = await update_service.get_settings(db)
    return UpdateSettingsResponse.model_validate(settings)


@router.put("/settings", response_model=UpdateSettingsResponse)
async def update_settings(
    settings_update: UpdateSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update settings."""
    settings = await update_service.update_settings(
        db=db,
        **settings_update.model_dump(exclude_none=True)
    )
    return UpdateSettingsResponse.model_validate(settings)
