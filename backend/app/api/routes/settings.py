import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user, get_current_user
from app.core.database import get_db
from app.core.files import write_text
from app.core.utils import get_client_ip
from app.models.audit_log import AuditLog
from app.models.setting import Setting
from app.models.user import User
from app.schemas.access_list import _check_redirect_url
from app.schemas.setting import SettingResponse, SettingsBulkUpdate, SettingUpdate
from app.services import ghostwire_analytics

router = APIRouter()


# Default settings
DEFAULT_SETTINGS = {
    "letsencrypt_email": "",
    "letsencrypt_staging": "false",
    "traffic_log_retention_days": "30",
    "threat_event_retention_days": "90",
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
    "abuseipdb_auto_report_enabled": "false",
    # Per-backend-server alerts: at most one down alert per server per window
    "upstream_alert_flap_minutes": "5",
}


# Secret values are write-only: every reader (admins included) gets a mask,
# and a masked value sent back unchanged leaves the stored secret alone.
SECRET_MASK = "\u2022\u2022\u2022\u2022"  # noqa: S105  not a secret: the mask shown in place of one
_SECRET_KEY_RE = re.compile(r"(password|secret|token|api_key|private_key|apikey|ingest_key)$")


def is_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY_RE.search(key or ""))


def mask_secret(key: str, value):
    """The masked form of a stored secret: "••••" plus the last 4 characters of a plain key."""
    if not value:
        return value
    if key.endswith("password") or len(value) < 12:
        return SECRET_MASK
    return SECRET_MASK + value[-4:]


def is_masked(value) -> bool:
    return isinstance(value, str) and value.startswith(SECRET_MASK)


def setting_out(setting: Setting) -> dict:
    value = setting.value
    if is_secret_key(setting.key):
        value = mask_secret(setting.key, value)
    return {
        "key": setting.key,
        "value": value,
        "description": setting.description,
        "updated_at": setting.updated_at,
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
    return [setting_out(s) for s in result.scalars().all()]


# NOTE: these specific paths must stay ABOVE the generic /{key} routes.
# FastAPI matches in declaration order, so /{key} would otherwise capture
# "default-site" first — which is exactly what happened: PUTs landed in the
# generic handler and wrote a junk settings row keyed "default-site" with an
# empty value, GETs returned that row instead of {behavior, redirect_url}, and
# the nginx default site was never regenerated.
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

    # Written into the default server block as `return 301 <url>;`.
    @field_validator("redirect_url")
    @classmethod
    def validate_redirect_url(cls, v: str) -> str:
        return _check_redirect_url(v) or ""


@router.put("/default-site")
async def update_default_site(
    data: DefaultSiteUpdate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update default site behavior and regenerate nginx config"""

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
    db.add(
        AuditLog(
            user_id=current_user.id,
            email=current_user.email,
            action="default_site_updated",
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details=f"Default site: {data.behavior}" + (f" -> {data.redirect_url}" if data.redirect_url else ""),
        )
    )
    await db.commit()

    # Regenerate and apply the default site config
    import os

    from app.core.config import settings as app_settings
    from app.services.openresty_service import (
        backup_configs,
        config_apply_lock,
        generate_default_site_config,
        reload_nginx,
        restore_configs,
        test_nginx_config,
    )

    async with config_apply_lock:
        # Backup current configs before writing the new default
        await asyncio.to_thread(backup_configs)

        config = await generate_default_site_config(db)
        await write_text(os.path.join(app_settings.nginx_config_path, "_default.conf"), config)

        # Test before reloading — roll back if invalid
        test_ok, test_msg = await asyncio.to_thread(test_nginx_config)
        if not test_ok:
            await asyncio.to_thread(restore_configs)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Default site config is invalid — rolled back. Error: {test_msg}",
            )

        # Reload nginx to apply
        success, message = await asyncio.to_thread(reload_nginx)
    if not success:
        return {"message": "Default site saved but nginx reload failed", "detail": message, "behavior": data.behavior}

    return {"message": "Default site updated and applied", "behavior": data.behavior}


# Ghostwire Analytics (system monitoring): admin only, with its own validation, and the ingest key
# encrypted and write-only. The generic /{key} routes refuse these keys (see _check_config_setting).
class AnalyticsSettingsChange(BaseModel):
    enabled: bool = False
    url: str = ""
    websiteId: str = ""
    traceSample: int = ghostwire_analytics.DEFAULT_TRACE_SAMPLE
    browser: bool = False
    replay: bool = False
    # Absent keeps the stored key, "" removes it.
    ingestKey: str | None = None


@router.get("/analytics")
async def get_analytics_settings(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """The Ghostwire Analytics settings, without the ingest key (only whether one is stored)."""
    return ghostwire_analytics.public_view(await ghostwire_analytics.load(db))


@router.put("/analytics")
async def update_analytics_settings(
    data: AnalyticsSettingsChange,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the Ghostwire Analytics settings. They apply within a minute, without a restart."""
    change = data.model_dump(exclude_unset=True)
    try:
        saved = await ghostwire_analytics.save(db, change)
    except ghostwire_analytics.AnalyticsSettingsError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)) from None

    key_note = ""
    if change.get("ingestKey") is not None:
        key_note = ", ingest key replaced" if change["ingestKey"].strip() else ", ingest key removed"
    db.add(
        AuditLog(
            user_id=current_user.id,
            email=current_user.email,
            action="analytics_settings_updated",
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details=f"Ghostwire Analytics monitoring {'on' if saved['enabled'] else 'off'}{key_note}",
        )
    )
    await db.commit()
    return saved


@router.post("/analytics/test")
async def check_analytics_connection(
    data: AnalyticsSettingsChange,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Check the values are well-formed and the Analytics URL answers. Saves nothing."""
    stored = await ghostwire_analytics.load(db)
    return await ghostwire_analytics.check_connection(data.model_dump(), stored_key=stored["ingest_key"])


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

    return setting_out(setting)


def _check_config_setting(key: str, value) -> None:
    """Settings the nginx config is generated from get the same checks as their own routes."""
    if ghostwire_analytics.is_analytics_key(key):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ghostwire Analytics settings are saved through /api/settings/analytics",
        )
    if key == "default_site_redirect_url" and value:
        try:
            _check_redirect_url(str(value))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from None
    if key == "default_site_behavior" and value not in (None, "congratulations", "redirect", "404", "444"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown default site behavior")


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    setting_data: SettingUpdate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update setting (admin only)"""
    _check_config_setting(key, setting_data.value)
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if not setting:
        # Create if it doesn't exist
        setting = Setting(key=key)
        db.add(setting)

    # Update fields (a secret sent back in its masked form is left as it is)
    for field, value in setting_data.model_dump(exclude_unset=True).items():
        if field == "value" and is_secret_key(key) and is_masked(value):
            continue
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

    return setting_out(setting)


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
        _check_config_setting(key, value)
    for key, value in settings_data.settings.items():
        if is_secret_key(key) and is_masked(value):
            continue
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

    return [setting_out(s) for s in updated_settings]


@router.post("/reload-nginx")
async def reload_nginx_endpoint(
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Reload nginx configuration via Docker socket SIGHUP"""
    from app.services.openresty_service import reload_nginx, test_nginx_config

    # Test config first so we don't reload a broken config
    test_ok, test_msg = await asyncio.to_thread(test_nginx_config)
    if not test_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nginx config test failed — not reloading. Error: {test_msg}",
        )

    success, message = await asyncio.to_thread(reload_nginx)
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
