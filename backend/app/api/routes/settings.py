from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.utils import get_client_ip
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
    "default_site_behavior": "congratulations",
    "default_site_redirect_url": "",
    "trusted_ips": "[]",
    "abuseipdb_api_key": "",
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
        ip_address=get_client_ip(request),
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
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated settings: {', '.join(settings_data.settings.keys())}",
    )
    db.add(audit_log)
    await db.commit()

    for setting in updated_settings:
        await db.refresh(setting)

    return updated_settings


@router.post("/reload-nginx")
async def reload_nginx_endpoint(
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Reload nginx configuration via Docker socket SIGHUP"""
    from app.services.openresty_service import reload_nginx, test_nginx_config

    # Test config first so we don't reload a broken config
    test_ok, test_msg = test_nginx_config()
    if not test_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nginx config test failed — not reloading. Error: {test_msg}",
        )

    success, message = reload_nginx()
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload nginx: {message}",
        )

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="nginx_reloaded",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_log)
    await db.commit()

    return {"message": "Nginx configuration reloaded successfully"}


@router.get("/default-site")
async def get_default_site(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current default site behavior settings"""
    behavior = "congratulations"
    redirect_url = ""

    result = await db.execute(select(Setting).where(Setting.key == "default_site_behavior"))
    setting = result.scalar_one_or_none()
    if setting:
        behavior = setting.value

    result = await db.execute(select(Setting).where(Setting.key == "default_site_redirect_url"))
    setting = result.scalar_one_or_none()
    if setting:
        redirect_url = setting.value

    return {"behavior": behavior, "redirect_url": redirect_url}


@router.put("/default-site")
async def update_default_site(
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update default site behavior and regenerate nginx config"""
    from pydantic import BaseModel, field_validator

    class DefaultSiteUpdate(BaseModel):
        behavior: str
        redirect_url: str = ""

        @field_validator("behavior")
        @classmethod
        def validate_behavior(cls, v: str) -> str:
            valid = ("congratulations", "redirect", "404", "444")
            if v not in valid:
                raise ValueError(f"Behavior must be one of: {', '.join(valid)}")
            return v

    body = await request.json()
    data = DefaultSiteUpdate(**body)

    # Validate redirect URL is provided when behavior is redirect
    if data.behavior == "redirect" and not data.redirect_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Redirect URL is required when behavior is 'redirect'",
        )

    # Save settings
    for key, value in [("default_site_behavior", data.behavior), ("default_site_redirect_url", data.redirect_url)]:
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            setting = Setting(key=key, value=value)
            db.add(setting)

    # Audit log
    db.add(AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="default_site_updated",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Default site: {data.behavior}" + (f" -> {data.redirect_url}" if data.redirect_url else ""),
    ))
    await db.commit()

    # Regenerate and apply the default site config
    from app.services.openresty_service import generate_default_site_config, reload_nginx, test_nginx_config, backup_configs, restore_configs
    import os
    from app.core.config import settings as app_settings

    # Backup current configs before writing the new default
    backup_configs()

    config = await generate_default_site_config(db)
    config_path = os.path.join(app_settings.nginx_config_path, "_default.conf")
    with open(config_path, "w") as f:
        f.write(config)

    # Test before reloading — roll back if invalid
    test_ok, test_msg = test_nginx_config()
    if not test_ok:
        restore_configs()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Default site config is invalid — rolled back. Error: {test_msg}",
        )

    # Reload nginx to apply
    success, message = reload_nginx()
    if not success:
        return {"message": "Default site saved but nginx reload failed", "detail": message, "behavior": data.behavior}

    return {"message": "Default site updated and applied", "behavior": data.behavior}
