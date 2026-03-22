from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import subprocess

from app.core.database import get_db
from app.models.user import User
from app.models.setting import Setting
from app.models.audit_log import AuditLog
from app.schemas.setting import SettingUpdate, SettingResponse, SettingsBulkUpdate
from app.api.deps import get_current_user, get_current_admin_user

router = APIRouter()


# Default settings
DEFAULT_SETTINGS = {
    "letsencrypt_email": "",
    "letsencrypt_staging": "false",
    "traffic_log_retention_days": "30",
    "audit_log_retention_days": "90",
    "default_http2_support": "true",
    "default_hsts_enabled": "false",
    "default_block_exploits": "true",
    "nginx_worker_processes": "auto",
    "nginx_worker_connections": "4096",
}


async def ensure_default_settings(db: AsyncSession):
    """Ensure default settings exist"""
    for key, value in DEFAULT_SETTINGS.items():
        result = await db.execute(select(Setting).where(Setting.key == key))
        if not result.scalar_one_or_none():
            setting = Setting(key=key, value=value)
            db.add(setting)
    await db.commit()


@router.get("/", response_model=list[SettingResponse])
async def list_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all settings"""
    await ensure_default_settings(db)

    result = await db.execute(select(Setting).order_by(Setting.key))
    return result.scalars().all()


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get setting by key"""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if not setting:
        # Return default if exists
        if key in DEFAULT_SETTINGS:
            setting = Setting(key=key, value=DEFAULT_SETTINGS[key])
            db.add(setting)
            await db.commit()
            await db.refresh(setting)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Setting not found",
            )

    return setting


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    setting_data: SettingUpdate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update setting (admin only)"""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if not setting:
        # Create if it doesn't exist
        setting = Setting(key=key)
        db.add(setting)

    # Update fields
    for field, value in setting_data.model_dump(exclude_unset=True).items():
        setattr(setting, field, value)

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="setting_updated",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                   (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated setting: {key}",
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(setting)

    return setting


@router.put("/", response_model=list[SettingResponse])
async def bulk_update_settings(
    settings_data: SettingsBulkUpdate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update settings (admin only)"""
    updated_settings = []

    for key, value in settings_data.settings.items():
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()

        if not setting:
            setting = Setting(key=key)
            db.add(setting)

        setting.value = value
        updated_settings.append(setting)

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="settings_bulk_updated",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                   (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated settings: {', '.join(settings_data.settings.keys())}",
    )
    db.add(audit_log)
    await db.commit()

    for setting in updated_settings:
        await db.refresh(setting)

    return updated_settings


@router.post("/reload-nginx")
async def reload_nginx(
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Reload nginx configuration"""
    try:
        # Test configuration first
        test_result = subprocess.run(
            ["nginx", "-t"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if test_result.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Nginx configuration test failed: {test_result.stderr}",
            )

        # Reload nginx
        reload_result = subprocess.run(
            ["nginx", "-s", "reload"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if reload_result.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to reload nginx: {reload_result.stderr}",
            )

        # Audit log
        audit_log = AuditLog(
            user_id=current_user.id,
            email=current_user.email,
            action="nginx_reloaded",
            ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                       (request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
        )
        db.add(audit_log)
        await db.commit()

        return {"message": "Nginx configuration reloaded successfully"}

    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nginx reload timed out",
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nginx binary not found",
        )
