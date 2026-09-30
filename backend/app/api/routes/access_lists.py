from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.cache import cached_json, cache_delete_prefix
from app.core.utils import get_client_ip
from app.models.user import User
from app.models.access_list import AccessList, AccessListEntry
from app.models.proxy_host import ProxyHost
from app.models.audit_log import AuditLog
from app.schemas.access_list import (
    AccessListCreate, AccessListUpdate, AccessListResponse,
    AccessListEntryCreate, AccessListEntryResponse
)
from app.api.deps import get_current_user, get_current_admin_user
from app.api.routes.proxy_hosts import validate_and_apply

router = APIRouter()


def _with_relations(query):
    return query.options(
        selectinload(AccessList.entries),
        selectinload(AccessList.proxy_hosts),
    )


async def _load_access_list(db: AsyncSession, list_id: str) -> AccessList:
    result = await db.execute(_with_relations(select(AccessList)).where(AccessList.id == list_id))
    access_list = result.scalar_one_or_none()
    if not access_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access list not found",
        )
    return access_list


async def _host_count(db: AsyncSession, list_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(ProxyHost).where(ProxyHost.access_list_id == list_id)
    )
    return int(result.scalar() or 0)


async def _save(db: AsyncSession, list_id: str) -> None:
    """Commit, or if hosts use this list, commit only once nginx has taken the new rules."""
    if await _host_count(db, list_id):
        ok, msg = await validate_and_apply(db)
        if not ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    else:
        await db.commit()
    await cache_delete_prefix("access_lists:")


@router.get("/", response_model=list[AccessListResponse])
async def list_access_lists(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all access lists (15s cache, invalidated on writes)."""
    cache_key = f"access_lists:list:{skip}:{limit}"

    async def _compute() -> dict:
        query = (
            _with_relations(select(AccessList))
            .order_by(AccessList.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        items_result = await db.execute(query)
        total_result = await db.execute(select(func.count()).select_from(AccessList))
        items = [AccessListResponse.model_validate(a, from_attributes=True).model_dump(mode="json")
                 for a in items_result.scalars().all()]
        return {"items": items, "total": int(total_result.scalar() or 0)}

    payload = await cached_json(cache_key, ttl=15, producer=_compute)
    response.headers["X-Total-Count"] = str(payload["total"])
    return payload["items"]


@router.post("/", response_model=AccessListResponse, status_code=status.HTTP_201_CREATED)
async def create_access_list(
    list_data: AccessListCreate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new access list"""
    access_list = AccessList(
        name=list_data.name,
        mode=list_data.mode,
        default_action=list_data.default_action,
        blocked_behavior=list_data.blocked_behavior,
        blocked_redirect_url=list_data.blocked_redirect_url,
    )
    db.add(access_list)
    await db.flush()

    # Add entries if provided
    if list_data.entries:
        for entry_data in list_data.entries:
            entry = AccessListEntry(
                access_list_id=access_list.id,
                **entry_data.model_dump()
            )
            db.add(entry)

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="access_list_created",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Created access list: {list_data.name}",
    )
    db.add(audit_log)
    await db.commit()
    await cache_delete_prefix("access_lists:")

    return await _load_access_list(db, access_list.id)


@router.get("/{list_id}", response_model=AccessListResponse)
async def get_access_list(
    list_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get access list by ID"""
    return await _load_access_list(db, list_id)


@router.put("/{list_id}", response_model=AccessListResponse)
async def update_access_list(
    list_id: str,
    list_data: AccessListUpdate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Update access list. Hosts using it get the new rules straight away."""
    access_list = await _load_access_list(db, list_id)

    changes = list_data.model_dump(exclude_unset=True, exclude={"entries"})
    for field, value in changes.items():
        setattr(access_list, field, value)

    if list_data.entries is not None:
        access_list.entries = [AccessListEntry(**e.model_dump()) for e in list_data.entries]

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="access_list_updated",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated access list: {access_list.name}",
    )
    db.add(audit_log)
    await _save(db, list_id)

    db.expunge_all()
    return await _load_access_list(db, list_id)


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_access_list(
    list_id: str,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete access list. Hosts using it are left open (no list)."""
    result = await db.execute(select(AccessList).where(AccessList.id == list_id))
    access_list = result.scalar_one_or_none()

    if not access_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access list not found",
        )

    in_use = await _host_count(db, list_id)

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="access_list_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted access list: {access_list.name}",
    )
    db.add(audit_log)

    await db.execute(
        update(ProxyHost).where(ProxyHost.access_list_id == list_id).values(access_list_id=None)
    )
    await db.delete(access_list)

    if in_use:
        ok, msg = await validate_and_apply(db)
        if not ok:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    else:
        await db.commit()
    await cache_delete_prefix("access_lists:")


# Entry management
@router.post("/{list_id}/entries", response_model=AccessListEntryResponse, status_code=status.HTTP_201_CREATED)
async def add_entry(
    list_id: str,
    entry_data: AccessListEntryCreate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Add entry to access list"""
    access_list = await _load_access_list(db, list_id)

    entry = AccessListEntry(**entry_data.model_dump())
    access_list.entries.append(entry)
    await db.flush()
    entry_id = entry.id

    await _save(db, list_id)

    result = await db.execute(select(AccessListEntry).where(AccessListEntry.id == entry_id))
    return result.scalar_one()


@router.delete("/{list_id}/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_entry(
    list_id: str,
    entry_id: str,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove entry from access list"""
    access_list = await _load_access_list(db, list_id)

    entry = next((e for e in access_list.entries if e.id == entry_id), None)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )

    access_list.entries.remove(entry)
    await _save(db, list_id)
