"""Config tooling for scripts and AI agents: dry-run previews, `nginx -t`, and a full reload.

    POST /api/config/preview  render a host's nginx config with proposed changes, plus a diff
                              against what nginx runs now. Saves nothing. (scope: read)
    POST /api/config/test     run `nginx -t` on the configs nginx has now. (scope: write:nginx)
    POST /api/config/reload   regenerate every host's config from the database, `nginx -t`,
                              reload; all-or-nothing like any save. (scope: write:nginx)
    GET  /api/audit-logs      recent changes, newest first. (scope: read)
"""
import difflib
import os
from types import SimpleNamespace
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_admin_user, get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.utils import get_client_ip
from app.models.access_list import AccessList
from app.models.audit_log import AuditLog
from app.models.certificate import Certificate
from app.models.auth_wall import AuthWall
from app.models.proxy_host import ProxyHost, ProxyLocation, UpstreamServer
from app.models.user import User
from app.schemas.proxy_host import ProxyHostCreate, ProxyHostUpdate

router = APIRouter()
audit_router = APIRouter()


class ConfigPreviewRequest(BaseModel):
    # Omit for a new host.
    host_id: Optional[str] = None
    # Fields as the proxy-host create (new host) or update (existing host) endpoint takes them.
    changes: dict[str, Any] = {}


def _column_defaults(model) -> dict[str, Any]:
    values = {}
    for column in model.__table__.columns:
        default = column.default
        values[column.name] = default.arg if default is not None and not callable(default.arg) else None
    return values


def _columns_of(obj) -> dict[str, Any]:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _server_ns(data: dict[str, Any]) -> SimpleNamespace:
    values = _column_defaults(UpstreamServer)
    values.update(data)
    values.setdefault("auto_down", False)
    return SimpleNamespace(**values)


def _validation_detail(e: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or 'body'}: {err['msg']}" for err in e.errors()
    )


@router.post("/preview")
async def preview_config(
    payload: ConfigPreviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The nginx config a host would get with `changes` applied, without saving anything.

    Rendered by the same generator a save uses. `nginx -t` is not run here (that needs the file
    on disk); a real save still runs it and keeps nothing if it fails.
    """
    from app.services.openresty_service import generate_server_block, set_trusted_proxy_ranges

    existing: ProxyHost | None = None
    if payload.host_id:
        existing = (await db.execute(
            select(ProxyHost)
            .options(selectinload(ProxyHost.upstream_servers), selectinload(ProxyHost.locations))
            .where(ProxyHost.id == payload.host_id)
        )).scalar_one_or_none()
        if existing is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy host not found")

    try:
        if existing is None:
            data = ProxyHostCreate(**payload.changes)
            values = _column_defaults(ProxyHost)
            values.update(data.model_dump(exclude={"upstream_servers", "locations"}))
            values["id"] = "preview-new-host"
            servers = [_server_ns(s.model_dump()) for s in data.upstream_servers or []]
            locations = [
                SimpleNamespace(**{**_column_defaults(ProxyLocation), **loc.model_dump(), "id": f"preview-{i}"})
                for i, loc in enumerate(data.locations or [])
            ]
        else:
            data = ProxyHostUpdate(**payload.changes)
            values = _columns_of(existing)
            values.update(data.model_dump(exclude_unset=True, exclude={"upstream_servers"}))
            current = {s.id: _columns_of(s) for s in existing.upstream_servers}
            if "upstream_servers" in data.model_fields_set and data.upstream_servers is not None:
                servers = []
                for item in data.upstream_servers:
                    fields = item.model_dump(exclude={"id"})
                    base = current.get(item.id, {}) if getattr(item, "id", None) else {}
                    servers.append(_server_ns({**base, **fields}))
            else:
                servers = [_server_ns(v) for v in current.values()]
            locations = list(existing.locations)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_validation_detail(e))

    # Related rows the generator reads, loaded for the (possibly changed) ids.
    access_list = None
    if values.get("access_list_id"):
        access_list = (await db.execute(
            select(AccessList).options(selectinload(AccessList.entries)).where(AccessList.id == values["access_list_id"])
        )).scalar_one_or_none()
        if access_list is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="access_list_id: no such access list")
    auth_wall = None
    if values.get("auth_wall_id"):
        auth_wall = (await db.execute(select(AuthWall).where(AuthWall.id == values["auth_wall_id"]))).scalar_one_or_none()
        if auth_wall is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="auth_wall_id: no such auth wall")
    cert = None
    if values.get("ssl_enabled") and values.get("certificate_id"):
        cert = (await db.execute(select(Certificate).where(Certificate.id == values["certificate_id"]))).scalar_one_or_none()
        if cert is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="certificate_id: no such certificate")

    cert_has_data = bool(cert and cert.certificate and cert.certificate_key)

    host = SimpleNamespace(
        **values,
        upstream_servers=servers,
        locations=locations,
        access_list=access_list,
        auth_wall=auth_wall,
        certificate=cert,
    )

    try:
        from app.services.trusted_proxy_service import get_ranges
        set_trusted_proxy_ranges(await get_ranges(db))
    except Exception:
        pass

    warnings: list[str] = []
    try:
        from app.services.load_balancing import check_lb_rules
        errors, lb_warnings = check_lb_rules(values.get("lb_method"), servers)
        warnings.extend(lb_warnings)
    except ImportError:  # older generator without load balancing
        errors = []

    try:
        rendered = generate_server_block(host, cert)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Could not render config: {e}")
    finally:
        # Nothing here may be saved.
        await db.rollback()

    if values.get("ssl_enabled") and not cert_has_data:
        warnings.append("SSL is on but the certificate has no data yet, so only the HTTP server block is rendered.")
    if not values.get("enabled", True):
        warnings.append("The host is disabled: nginx would get no config for it until it is enabled.")

    current_text = None
    if existing is not None:
        path = os.path.join(settings.nginx_config_path, f"{payload.host_id}.conf")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8", newline="") as f:
                current_text = f.read()

    diff = "".join(difflib.unified_diff(
        (current_text or "").splitlines(keepends=True),
        rendered.splitlines(keepends=True),
        fromfile="running" if current_text is not None else "/dev/null",
        tofile="proposed",
    ))

    return {
        "host_id": payload.host_id,
        "config": rendered,
        "diff": diff,
        "running_config_found": current_text is not None,
        "changed": current_text != rendered,
        "errors": errors,
        "warnings": warnings,
    }


@router.post("/test")
async def test_config(
    request: Request,
    current_user: User = Depends(get_current_admin_user),
):
    """Run `nginx -t` against the configuration nginx has now."""
    from app.services.openresty_service import test_nginx_config

    ok, output = test_nginx_config()
    return {"ok": ok, "output": output}


@router.post("/reload")
async def reload_config(
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate every config from the database, test and reload — all or nothing."""
    from app.api.routes.proxy_hosts import validate_and_apply

    db.add(AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="nginx_regenerated",
        details="Regenerated all host configs and reloaded nginx",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))
    ok, message = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    return {"ok": True, "message": message}


@audit_router.get("/")
async def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    action: Optional[str] = Query(None, max_length=100),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Recent audit-log entries, newest first; `action` filters by prefix (e.g. "proxy_host")."""
    query = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    if action:
        query = query.where(AuditLog.action.startswith(action))
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": r.id,
            "timestamp": r.timestamp,
            "action": r.action,
            "details": r.details,
            "email": r.email,
            "ip_address": r.ip_address,
        }
        for r in rows
    ]
