import os
import re
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.cache import cached_json, cache_delete_prefix
from app.core.utils import get_client_ip
from app.models.user import User
from app.models.proxy_host import ProxyHost, UpstreamServer, UpstreamServerEvent, ProxyLocation
from app.models.audit_log import AuditLog
from app.schemas.proxy_host import (
    ProxyHostCreate, ProxyHostUpdate, ProxyHostResponse,
    UpstreamServerCreate, UpstreamServerUpdate, UpstreamServerUpsert, UpstreamServerResponse,
    UpstreamPreviewRequest, UpstreamPreviewResponse, UpstreamCheckResult, UpstreamServerEventResponse,
    ProxyLocationCreate, ProxyLocationUpdate, ProxyLocationResponse,
    LocationReorderRequest
)
from app.services.load_balancing import check_lb_rules
from app.api.deps import get_current_user, get_current_admin_user
from app.services.openresty_service import (
    generate_all_configs, reload_nginx, remove_config,
    backup_configs, restore_configs, test_nginx_config,
    generate_upstream_block, generate_upstream_connection_map,
    generate_upstream_location_directives, upstream_name,
)

router = APIRouter()


def _enforce_lb_rules(method: str | None, servers) -> None:
    """Refuse an upstream group nginx would reject (or that can't serve)."""
    errors, _warnings = check_lb_rules(method, servers)
    if errors:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=" ".join(errors))


_HEALTH_FIELDS = ("last_check_at", "last_error", "last_latency_ms")


def _reset_health(server: UpstreamServer) -> None:
    for name in _HEALTH_FIELDS:
        setattr(server, name, None)
    server.last_status = "unknown"
    server.auto_down = False


def _replace_upstream_servers(host: ProxyHost, items: list[UpstreamServerUpsert]) -> None:
    """Make the host's servers match `items`, keeping saved rows by id.

    Rows that keep their id keep their health history (unless their address
    changed); rows left out are deleted by the relationship's delete-orphan
    cascade when the session flushes.
    """
    existing = {s.id: s for s in host.upstream_servers}
    servers = []
    for item in items:
        data = item.model_dump(exclude={"id"})
        server = existing.pop(item.id, None) if item.id else None
        if server is None:
            server = UpstreamServer(proxy_host_id=host.id, **data)
        else:
            if (server.host, server.port) != (data["host"], data["port"]):
                _reset_health(server)
            for field, value in data.items():
                setattr(server, field, value)
        servers.append(server)
    host.upstream_servers = servers


async def _load_host(db: AsyncSession, host_id: str) -> ProxyHost | None:
    result = await db.execute(
        select(ProxyHost)
        .options(
            selectinload(ProxyHost.upstream_servers),
            selectinload(ProxyHost.locations)
        )
        .where(ProxyHost.id == host_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def validate_and_apply(
    db: AsyncSession,
    remove_config_ids: list[str] | None = None,
) -> tuple[bool, str]:
    """Apply pending changes to nginx, committing them only if the config is valid.

    Pending changes are flushed so the generated config reflects them, but they
    are not committed until `nginx -t` has passed and nginx has reloaded. If any
    step fails, both the database and the on-disk config are rolled back, so the
    UI never shows a change as saved that nginx isn't actually running.
    """
    try:
        await db.flush()
    except Exception as e:
        await db.rollback()
        return False, f"Could not save changes: {e}"

    # 1. Back up the current working configs so a bad config can be undone
    backup_configs()

    # 2. Generate the candidate config from the flushed (uncommitted) state
    try:
        await generate_all_configs(db)
        for host_id in remove_config_ids or []:
            await remove_config(host_id)
    except Exception as e:
        restore_configs()
        await db.rollback()
        return False, f"Error generating nginx config — nothing was saved. Detail: {e}"

    # 3. Validate it. test_nginx_config returns nginx's own output, which names
    #    the offending file, line and directive — pass it straight through.
    test_ok, test_msg = test_nginx_config()
    if not test_ok:
        restore_configs()
        await db.rollback()
        return False, (
            "Config validation failed — nothing was saved and nginx is unchanged.\n\n"
            f"{test_msg}"
        )

    # 4. Config is valid — reload nginx
    reload_ok, reload_msg = reload_nginx()
    if not reload_ok:
        restore_configs()
        await db.rollback()
        return False, f"Config is valid but nginx reload failed — nothing was saved. {reload_msg}"

    # 5. Only now is the change real
    await db.commit()

    # Invalidate cached list responses so the UI sees fresh data
    # without waiting for the 15s TTL.
    await cache_delete_prefix("proxy_hosts:")

    return True, "Configuration validated and applied"


@router.get("/", response_model=list[ProxyHostResponse])
async def list_proxy_hosts(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    enabled: bool | None = None,
    search: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all proxy hosts (15s Redis cache, invalidated on writes)."""
    cache_key = f"proxy_hosts:list:{skip}:{limit}:{enabled}:{search or ''}"

    async def _compute() -> dict:
        query = select(ProxyHost).options(
            selectinload(ProxyHost.upstream_servers),
            selectinload(ProxyHost.locations)
        )
        count_query = select(func.count()).select_from(ProxyHost)

        if enabled is not None:
            query = query.where(ProxyHost.enabled == enabled)
            count_query = count_query.where(ProxyHost.enabled == enabled)

        if search:
            query = query.where(ProxyHost.forward_host.ilike(f"%{search}%"))
            count_query = count_query.where(ProxyHost.forward_host.ilike(f"%{search}%"))

        query = query.order_by(ProxyHost.created_at.desc()).offset(skip).limit(limit)
        items_result = await db.execute(query)
        total_result = await db.execute(count_query)

        items = [ProxyHostResponse.model_validate(h, from_attributes=True).model_dump(mode="json")
                 for h in items_result.scalars().all()]
        return {"items": items, "total": int(total_result.scalar() or 0)}

    payload = await cached_json(cache_key, ttl=15, producer=_compute)
    response.headers["X-Total-Count"] = str(payload["total"])
    return payload["items"]


@router.post("/", response_model=ProxyHostResponse, status_code=status.HTTP_201_CREATED)
async def create_proxy_host(
    host_data: ProxyHostCreate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new proxy host"""
    # Every field the schema carries; nested lists are added below.
    _enforce_lb_rules(host_data.lb_method, host_data.upstream_servers or [])
    host = ProxyHost(**host_data.model_dump(exclude={"upstream_servers", "locations"}))
    db.add(host)
    await db.flush()

    # Add upstream servers if provided
    if host_data.upstream_servers:
        for server_data in host_data.upstream_servers:
            server = UpstreamServer(
                proxy_host_id=host.id,
                **server_data.model_dump()
            )
            db.add(server)

    # Add locations if provided
    if host_data.locations:
        for loc_data in host_data.locations:
            location = ProxyLocation(
                proxy_host_id=host.id,
                **loc_data.model_dump()
            )
            db.add(location)

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="proxy_host_created",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Created proxy host: {', '.join(host_data.domain_names)}",
    )
    db.add(audit_log)

    # Nothing is committed unless the generated config passes nginx -t
    ok, msg = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    # Reload with relationships
    result = await db.execute(
        select(ProxyHost)
        .options(
            selectinload(ProxyHost.upstream_servers),
            selectinload(ProxyHost.locations)
        )
        .where(ProxyHost.id == host.id)
    )
    host = result.scalar_one()

    return host


@router.get("/{host_id}/config")
async def get_proxy_host_config(
    host_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The host's nginx config file exactly as it is on disk.

    nginx reads this same file (the directory is shared with it), and it is only
    written just before a reload (restored if the reload fails), so it is what
    nginx is running. Unsaved edits in the dialog are not in it.
    """
    result = await db.execute(select(ProxyHost.id, ProxyHost.enabled).where(ProxyHost.id == host_id))
    row = result.one_or_none()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy host not found",
        )

    # Built from the stored id, never the raw path parameter
    path = os.path.join(settings.nginx_config_path, f"{row.id}.conf")
    if not os.path.isfile(path):
        return {"exists": False, "enabled": row.enabled, "path": path, "content": None, "modified_at": None}

    with open(path, "r", encoding="utf-8", newline="") as f:
        content = f.read()
    modified_at = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    return {"exists": True, "enabled": row.enabled, "path": path, "content": content, "modified_at": modified_at}


@router.get("/{host_id}", response_model=ProxyHostResponse)
async def get_proxy_host(
    host_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get proxy host by ID"""
    result = await db.execute(
        select(ProxyHost)
        .options(
            selectinload(ProxyHost.upstream_servers),
            selectinload(ProxyHost.locations)
        )
        .where(ProxyHost.id == host_id)
    )
    host = result.scalar_one_or_none()

    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy host not found",
        )

    return host


@router.put("/{host_id}", response_model=ProxyHostResponse)
async def update_proxy_host(
    host_id: str,
    host_data: ProxyHostUpdate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update proxy host"""
    result = await db.execute(
        select(ProxyHost)
        .options(
            selectinload(ProxyHost.upstream_servers),
            selectinload(ProxyHost.locations)
        )
        .where(ProxyHost.id == host_id)
    )
    host = result.scalar_one_or_none()

    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy host not found",
        )

    # Update fields
    updates = host_data.model_dump(exclude_unset=True, exclude={"upstream_servers"})
    for field, value in updates.items():
        setattr(host, field, value)

    if host_data.upstream_servers is not None:
        _enforce_lb_rules(host.lb_method, host_data.upstream_servers)
        _replace_upstream_servers(host, host_data.upstream_servers)
    else:
        _enforce_lb_rules(host.lb_method, host.upstream_servers)

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="proxy_host_updated",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated proxy host: {host_id}",
    )
    db.add(audit_log)

    # Nothing is committed unless the generated config passes nginx -t
    ok, msg = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    # Re-read with relationships: a refresh would leave them to lazy-load,
    # which async sessions can't do during serialisation.
    return await _load_host(db, host_id)


@router.delete("/{host_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proxy_host(
    host_id: str,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete proxy host"""
    result = await db.execute(select(ProxyHost).where(ProxyHost.id == host_id))
    host = result.scalar_one_or_none()

    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy host not found",
        )

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="proxy_host_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted proxy host: {host_id}",
    )
    db.add(audit_log)

    await db.delete(host)

    # The regenerated set already excludes this host; its stale .conf file is
    # removed as part of the same validated, all-or-nothing apply.
    ok, msg = await validate_and_apply(db, remove_config_ids=[host_id])
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post("/{host_id}/enable", response_model=ProxyHostResponse)
async def enable_proxy_host(
    host_id: str,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Enable proxy host"""
    result = await db.execute(
        select(ProxyHost)
        .options(
            selectinload(ProxyHost.upstream_servers),
            selectinload(ProxyHost.locations)
        )
        .where(ProxyHost.id == host_id)
    )
    host = result.scalar_one_or_none()

    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy host not found",
        )

    host.enabled = True

    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="proxy_host_enabled",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Enabled proxy host: {host_id}",
    )
    db.add(audit_log)

    # Nothing is committed unless the generated config passes nginx -t
    ok, msg = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    await db.refresh(host)

    return host


@router.post("/{host_id}/disable", response_model=ProxyHostResponse)
async def disable_proxy_host(
    host_id: str,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable proxy host"""
    result = await db.execute(
        select(ProxyHost)
        .options(
            selectinload(ProxyHost.upstream_servers),
            selectinload(ProxyHost.locations)
        )
        .where(ProxyHost.id == host_id)
    )
    host = result.scalar_one_or_none()

    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy host not found",
        )

    host.enabled = False

    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="proxy_host_disabled",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Disabled proxy host: {host_id}",
    )
    db.add(audit_log)

    # Nothing is committed unless the generated config passes nginx -t
    ok, msg = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    await db.refresh(host)

    return host


# Upstream servers (load balancing)
@router.post("/upstream-preview", response_model=UpstreamPreviewResponse)
async def preview_upstream(
    preview: UpstreamPreviewRequest,
    current_user: User = Depends(get_current_user),
):
    """Render the upstream block for the editor's unsaved state.

    Uses the same generator the real config does, so the admin sees exactly
    what nginx will get. Nothing is saved or reloaded.
    """
    errors, warnings = check_lb_rules(preview.lb_method, preview.servers)
    # The id only names the upstream in the preview text; keep it to UUID characters.
    host_id = preview.host_id if preview.host_id and re.fullmatch(r"[A-Za-z0-9-]{1,36}", preview.host_id) else "new-host"
    host = SimpleNamespace(
        id=host_id,
        lb_method=preview.lb_method,
        upstream_keepalive=preview.upstream_keepalive,
        lb_auto_down=preview.lb_auto_down,
        websockets_support=preview.websockets_support,
        upstream_servers=[SimpleNamespace(auto_down=False, **srv.model_dump(exclude={"id"})) for srv in preview.servers],
    )
    block = generate_upstream_block(host)
    connection_map = generate_upstream_connection_map(host)
    if connection_map:
        block = f"{connection_map}\n\n{block}"
    location = ""
    if block:
        # The parts of the default location that load balancing adds; the
        # rest (headers, timeouts, WAF) is unchanged and elided.
        location = "\n".join([
            "location / {",
            f"    proxy_pass {preview.forward_scheme}://{upstream_name(host)};",
            "    proxy_http_version 1.1;",
            *generate_upstream_location_directives(host, indent="    "),
            "    # ... headers, timeouts and the rest as usual",
            "}",
        ])
    return UpstreamPreviewResponse(
        upstream_block=block,
        location_directives=location,
        errors=errors,
        warnings=warnings,
    )


@router.get("/{host_id}/upstreams", response_model=list[UpstreamServerResponse])
async def list_upstream_servers(
    host_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The host's upstream servers with their latest health."""
    host = await _load_host(db, host_id)
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy host not found")
    return host.upstream_servers


@router.post("/{host_id}/upstreams", response_model=UpstreamServerResponse, status_code=status.HTTP_201_CREATED)
async def add_upstream_server(
    host_id: str,
    server_data: UpstreamServerCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Add an upstream server to a proxy host"""
    host = await _load_host(db, host_id)
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy host not found",
        )

    _enforce_lb_rules(host.lb_method, [*host.upstream_servers, server_data])

    server = UpstreamServer(
        proxy_host_id=host_id,
        **server_data.model_dump()
    )
    host.upstream_servers.append(server)

    # Upstream changes alter the generated upstream block, so they go through
    # the same validate-then-commit path as every other config change.
    ok, msg = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    await db.refresh(server)
    return server


@router.api_route("/{host_id}/upstreams/{server_id}", methods=["PUT", "PATCH"], response_model=UpstreamServerResponse)
async def update_upstream_server(
    host_id: str,
    server_id: str,
    server_data: UpstreamServerUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Change an upstream server; only the fields sent are updated."""
    host = await _load_host(db, host_id)
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy host not found")
    server = next((s for s in host.upstream_servers if s.id == server_id), None)
    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upstream server not found")

    changes = server_data.model_dump(exclude_unset=True)
    for field in ("host", "port", "weight", "max_fails", "fail_timeout", "backup", "down", "enabled"):
        if field in changes and changes[field] is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"{field} can't be null")
    moved = ("host" in changes and changes["host"] != server.host) or ("port" in changes and changes["port"] != server.port)
    for field, value in changes.items():
        setattr(server, field, value)
    if moved:
        _reset_health(server)

    _enforce_lb_rules(host.lb_method, host.upstream_servers)

    ok, msg = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    await db.refresh(server)
    return server


@router.delete("/{host_id}/upstreams/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_upstream_server(
    host_id: str,
    server_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove an upstream server from a proxy host.

    Removing the last one returns the host to its single forward host.
    """
    host = await _load_host(db, host_id)
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy host not found")
    server = next((s for s in host.upstream_servers if s.id == server_id), None)
    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upstream server not found",
        )

    remaining = [s for s in host.upstream_servers if s.id != server_id]
    _enforce_lb_rules(host.lb_method, remaining)
    host.upstream_servers.remove(server)

    # Upstream changes alter the generated upstream block, so they go through
    # the same validate-then-commit path as every other config change.
    ok, msg = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.get("/{host_id}/upstream-events", response_model=list[UpstreamServerEventResponse])
async def list_upstream_events(
    host_id: str,
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recent backend down/recovered events for this host, newest first."""
    exists = (await db.execute(select(ProxyHost.id).where(ProxyHost.id == host_id))).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy host not found")
    result = await db.execute(
        select(UpstreamServerEvent)
        .where(UpstreamServerEvent.proxy_host_id == host_id)
        .order_by(UpstreamServerEvent.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


@router.post("/{host_id}/upstreams/check", response_model=list[UpstreamCheckResult])
async def check_upstream_servers_now(
    host_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Probe every enabled upstream server of this host right now.

    Only the configured host:port of each server is contacted (no redirects
    followed), with the host's health-check type, path and timeout.
    """
    from app.services.health_service import check_upstream_servers_now as _check_now

    host = await _load_host(db, host_id)
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy host not found")
    results = await _check_now(db, host)
    await cache_delete_prefix("proxy_hosts:")
    return results


# ============================================================================
# Location management endpoints
# ============================================================================

@router.get("/{host_id}/locations", response_model=list[ProxyLocationResponse])
async def list_locations(
    host_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all locations for a proxy host"""
    # Verify host exists
    result = await db.execute(select(ProxyHost).where(ProxyHost.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy host not found",
        )

    result = await db.execute(
        select(ProxyLocation)
        .where(ProxyLocation.proxy_host_id == host_id)
        .order_by(ProxyLocation.priority.desc())
    )
    return result.scalars().all()


@router.post("/{host_id}/locations", response_model=ProxyLocationResponse, status_code=status.HTTP_201_CREATED)
async def create_location(
    host_id: str,
    location_data: ProxyLocationCreate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new location for a proxy host"""
    # Verify host exists
    result = await db.execute(select(ProxyHost).where(ProxyHost.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy host not found",
        )

    location = ProxyLocation(
        proxy_host_id=host_id,
        **location_data.model_dump()
    )
    db.add(location)

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="location_created",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Created location '{location_data.path}' for host {host_id}",
    )
    db.add(audit_log)

    # Nothing is committed unless the generated config passes nginx -t
    ok, msg = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    await db.refresh(location)

    return location


@router.get("/{host_id}/locations/{location_id}", response_model=ProxyLocationResponse)
async def get_location(
    host_id: str,
    location_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific location"""
    result = await db.execute(
        select(ProxyLocation).where(
            (ProxyLocation.id == location_id) &
            (ProxyLocation.proxy_host_id == host_id)
        )
    )
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        )

    return location


@router.put("/{host_id}/locations/{location_id}", response_model=ProxyLocationResponse)
async def update_location(
    host_id: str,
    location_id: str,
    location_data: ProxyLocationUpdate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a location"""
    result = await db.execute(
        select(ProxyLocation).where(
            (ProxyLocation.id == location_id) &
            (ProxyLocation.proxy_host_id == host_id)
        )
    )
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        )

    # Update fields
    for field, value in location_data.model_dump(exclude_unset=True).items():
        setattr(location, field, value)

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="location_updated",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated location {location_id} for host {host_id}",
    )
    db.add(audit_log)

    # Nothing is committed unless the generated config passes nginx -t
    ok, msg = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    await db.refresh(location)

    return location


@router.delete("/{host_id}/locations/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_location(
    host_id: str,
    location_id: str,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a location"""
    result = await db.execute(
        select(ProxyLocation).where(
            (ProxyLocation.id == location_id) &
            (ProxyLocation.proxy_host_id == host_id)
        )
    )
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        )

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="location_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted location {location_id} for host {host_id}",
    )
    db.add(audit_log)

    await db.delete(location)

    # Nothing is committed unless the generated config passes nginx -t
    ok, msg = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.post("/{host_id}/locations/reorder", response_model=list[ProxyLocationResponse])
async def reorder_locations(
    host_id: str,
    reorder_data: LocationReorderRequest,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Reorder locations by updating their priorities"""
    # Verify host exists
    result = await db.execute(select(ProxyHost).where(ProxyHost.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy host not found",
        )

    # Update priorities
    for item in reorder_data.locations:
        result = await db.execute(
            select(ProxyLocation).where(
                (ProxyLocation.id == item.id) &
                (ProxyLocation.proxy_host_id == host_id)
            )
        )
        location = result.scalar_one_or_none()
        if location:
            location.priority = item.priority

    # Nothing is committed unless the generated config passes nginx -t
    ok, msg = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

    # Fetch updated locations
    result = await db.execute(
        select(ProxyLocation)
        .where(ProxyLocation.proxy_host_id == host_id)
        .order_by(ProxyLocation.priority.desc())
    )
    locations = result.scalars().all()

    return locations
