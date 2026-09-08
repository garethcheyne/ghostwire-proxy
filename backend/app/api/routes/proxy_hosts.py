from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.cache import cached_json, cache_delete_prefix
from app.core.utils import get_client_ip
from app.models.user import User
from app.models.proxy_host import ProxyHost, UpstreamServer, ProxyLocation
from app.models.audit_log import AuditLog
from app.schemas.proxy_host import (
    ProxyHostCreate, ProxyHostUpdate, ProxyHostResponse,
    UpstreamServerCreate, UpstreamServerResponse,
    ProxyLocationCreate, ProxyLocationUpdate, ProxyLocationResponse,
    LocationReorderRequest
)
from app.api.deps import get_current_user, get_current_admin_user
from app.services.openresty_service import (
    generate_all_configs, reload_nginx, remove_config,
    backup_configs, restore_configs, test_nginx_config,
)

router = APIRouter()


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
    # Create proxy host with all fields
    host = ProxyHost(
        domain_names=host_data.domain_names,
        forward_scheme=host_data.forward_scheme,
        forward_host=host_data.forward_host,
        forward_port=host_data.forward_port,
        ssl_enabled=host_data.ssl_enabled,
        ssl_force=host_data.ssl_force,
        certificate_id=host_data.certificate_id,
        http2_support=host_data.http2_support,
        hsts_enabled=host_data.hsts_enabled,
        hsts_subdomains=host_data.hsts_subdomains,
        websockets_support=host_data.websockets_support,
        block_exploits=host_data.block_exploits,
        access_list_id=host_data.access_list_id,
        auth_wall_id=host_data.auth_wall_id,
        advanced_config=host_data.advanced_config,
        server_advanced_config=host_data.server_advanced_config,
        client_max_body_size=host_data.client_max_body_size,
        proxy_buffering=host_data.proxy_buffering,
        proxy_buffer_size=host_data.proxy_buffer_size,
        proxy_buffers=host_data.proxy_buffers,
        cache_enabled=host_data.cache_enabled,
        cache_valid=host_data.cache_valid,
        cache_bypass=host_data.cache_bypass,
        rate_limit_enabled=host_data.rate_limit_enabled,
        rate_limit_requests=host_data.rate_limit_requests,
        rate_limit_period=host_data.rate_limit_period,
        rate_limit_burst=host_data.rate_limit_burst,
        custom_error_pages=host_data.custom_error_pages,
        traffic_logging_enabled=host_data.traffic_logging_enabled,
        enabled=host_data.enabled,
    )
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
    for field, value in host_data.model_dump(exclude_unset=True).items():
        setattr(host, field, value)

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

    await db.refresh(host)

    return host


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


# Upstream servers management
@router.post("/{host_id}/upstreams", response_model=UpstreamServerResponse, status_code=status.HTTP_201_CREATED)
async def add_upstream_server(
    host_id: str,
    server_data: UpstreamServerCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Add upstream server to proxy host"""
    result = await db.execute(select(ProxyHost).where(ProxyHost.id == host_id))
    host = result.scalar_one_or_none()

    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Proxy host not found",
        )

    server = UpstreamServer(
        proxy_host_id=host_id,
        **server_data.model_dump()
    )
    db.add(server)

    # Upstream changes alter the generated upstream block, so they go through
    # the same validate-then-commit path as every other config change.
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
    """Remove upstream server from proxy host"""
    result = await db.execute(
        select(UpstreamServer).where(
            (UpstreamServer.id == server_id) &
            (UpstreamServer.proxy_host_id == host_id)
        )
    )
    server = result.scalar_one_or_none()

    if not server:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upstream server not found",
        )

    await db.delete(server)

    # Upstream changes alter the generated upstream block, so they go through
    # the same validate-then-commit path as every other config change.
    ok, msg = await validate_and_apply(db)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


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
