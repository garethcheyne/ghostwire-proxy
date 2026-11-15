"""Groups and ordering for the Hosts page.

Layout only: groups and sort orders never reach nginx, so these routes commit
directly instead of going through validate_and_apply. Mounted under
/api/proxy-hosts/groups so API keys need the same scopes as for hosts.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user, get_current_user
from app.core.cache import cache_delete_prefix
from app.core.database import get_db
from app.core.utils import get_client_ip
from app.models.audit_log import AuditLog
from app.models.proxy_host import ProxyHost, ProxyHostGroup
from app.models.user import User
from app.schemas.proxy_host import (
    HostLayoutRequest,
    ProxyHostGroupCreate,
    ProxyHostGroupResponse,
    ProxyHostGroupUpdate,
)

router = APIRouter()


def _audit(db: AsyncSession, user: User, request: Request, action: str, details: str) -> None:
    db.add(
        AuditLog(
            user_id=user.id,
            email=user.email,
            action=action,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details=details,
        )
    )


async def _name_taken(db: AsyncSession, name: str, except_id: str | None = None) -> bool:
    query = select(ProxyHostGroup.id).where(func.lower(ProxyHostGroup.name) == name.lower())
    if except_id:
        query = query.where(ProxyHostGroup.id != except_id)
    return (await db.execute(query)).first() is not None


async def _commit(db: AsyncSession) -> None:
    await db.commit()
    # Host list responses carry group_id/sort_order and are cached for 15 s.
    await cache_delete_prefix("proxy_hosts:")


@router.get("", response_model=list[ProxyHostGroupResponse])
@router.get("/", response_model=list[ProxyHostGroupResponse], include_in_schema=False)
async def list_groups(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Every group, in page order."""
    result = await db.execute(select(ProxyHostGroup).order_by(ProxyHostGroup.sort_order, ProxyHostGroup.name))
    return result.scalars().all()


@router.post("", response_model=ProxyHostGroupResponse, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=ProxyHostGroupResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def create_group(
    data: ProxyHostGroupCreate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a group at the bottom of the page."""
    if await _name_taken(db, data.name):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A group called {data.name!r} already exists")
    last = (await db.execute(select(func.max(ProxyHostGroup.sort_order)))).scalar()
    group = ProxyHostGroup(name=data.name, sort_order=(last + 1) if last is not None else 0)
    db.add(group)
    _audit(db, current_user, request, "proxy_host_group_created", f"Created host group: {data.name}")
    await _commit(db)
    await db.refresh(group)
    return group


@router.put("/layout", status_code=status.HTTP_204_NO_CONTENT)
async def save_layout(
    data: HostLayoutRequest,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the order of groups and of the hosts within them, and which group each host is in."""
    group_ids = set((await db.execute(select(ProxyHostGroup.id))).scalars().all())
    host_ids = set((await db.execute(select(ProxyHost.id))).scalars().all())

    seen_groups: list[str] = []
    seen_hosts: list[str] = []
    for section in data.sections:
        if section.group_id is not None:
            seen_groups.append(section.group_id)
        seen_hosts.extend(section.host_ids)

    # Ungrouped (null) may appear at most once; groups and hosts exactly once.
    null_sections = sum(1 for s in data.sections if s.group_id is None)
    if (
        null_sections > 1
        or len(seen_groups) != len(set(seen_groups))
        or set(seen_groups) != group_ids
        or len(seen_hosts) != len(set(seen_hosts))
        or set(seen_hosts) != host_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The host list changed since this page loaded. Refresh and try again.",
        )

    order = 0
    for section in data.sections:
        if section.group_id is not None:
            await db.execute(
                update(ProxyHostGroup).where(ProxyHostGroup.id == section.group_id).values(sort_order=order)
            )
            order += 1
        for position, host_id in enumerate(section.host_ids):
            await db.execute(
                update(ProxyHost)
                .where(ProxyHost.id == host_id)
                .values(
                    group_id=section.group_id,
                    sort_order=position,
                    # updated_at tracks config changes; a reorder isn't one.
                    updated_at=ProxyHost.updated_at,
                )
                .execution_options(synchronize_session=False)
            )

    _audit(db, current_user, request, "proxy_host_layout_updated", "Reordered the host list")
    await _commit(db)


@router.put("/{group_id}", response_model=ProxyHostGroupResponse)
async def update_group(
    group_id: str,
    data: ProxyHostGroupUpdate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Rename a group."""
    group = await db.get(ProxyHostGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    if data.name is not None and data.name != group.name:
        if await _name_taken(db, data.name, except_id=group_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=f"A group called {data.name!r} already exists"
            )
        _audit(db, current_user, request, "proxy_host_group_updated", f"Renamed host group {group.name} to {data.name}")
        group.name = data.name
        await _commit(db)
        await db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: str,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a group. Its hosts stay, moved to the end of Ungrouped in their current order."""
    group = await db.get(ProxyHostGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    last = (await db.execute(select(func.max(ProxyHost.sort_order)).where(ProxyHost.group_id.is_(None)))).scalar()
    start = (last + 1) if last is not None else 0
    members = (
        (await db.execute(select(ProxyHost.id).where(ProxyHost.group_id == group_id).order_by(ProxyHost.sort_order)))
        .scalars()
        .all()
    )
    for offset, host_id in enumerate(members):
        await db.execute(
            update(ProxyHost)
            .where(ProxyHost.id == host_id)
            .values(group_id=None, sort_order=start + offset, updated_at=ProxyHost.updated_at)
            .execution_options(synchronize_session=False)
        )

    _audit(db, current_user, request, "proxy_host_group_deleted", f"Deleted host group: {group.name}")
    await db.delete(group)
    await _commit(db)
