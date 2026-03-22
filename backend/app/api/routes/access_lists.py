from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.user import User
from app.models.access_list import AccessList, AccessListEntry
from app.models.audit_log import AuditLog
from app.schemas.access_list import (
    AccessListCreate, AccessListUpdate, AccessListResponse,
    AccessListEntryCreate, AccessListEntryResponse
)
from app.api.deps import get_current_user

router = APIRouter()


@router.get("/", response_model=list[AccessListResponse])
async def list_access_lists(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all access lists"""
    query = (
        select(AccessList)
        .options(selectinload(AccessList.entries))
        .order_by(AccessList.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=AccessListResponse, status_code=status.HTTP_201_CREATED)
async def create_access_list(
    list_data: AccessListCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new access list"""
    access_list = AccessList(
        name=list_data.name,
        mode=list_data.mode,
        default_action=list_data.default_action,
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
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                   (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Created access list: {list_data.name}",
    )
    db.add(audit_log)
    await db.commit()

    # Reload with entries
    result = await db.execute(
        select(AccessList)
        .options(selectinload(AccessList.entries))
        .where(AccessList.id == access_list.id)
    )
    return result.scalar_one()


@router.get("/{list_id}", response_model=AccessListResponse)
async def get_access_list(
    list_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get access list by ID"""
    result = await db.execute(
        select(AccessList)
        .options(selectinload(AccessList.entries))
        .where(AccessList.id == list_id)
    )
    access_list = result.scalar_one_or_none()

    if not access_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access list not found",
        )

    return access_list


@router.put("/{list_id}", response_model=AccessListResponse)
async def update_access_list(
    list_id: str,
    list_data: AccessListUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update access list"""
    result = await db.execute(
        select(AccessList)
        .options(selectinload(AccessList.entries))
        .where(AccessList.id == list_id)
    )
    access_list = result.scalar_one_or_none()

    if not access_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access list not found",
        )

    # Update fields
    for field, value in list_data.model_dump(exclude_unset=True).items():
        setattr(access_list, field, value)

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="access_list_updated",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                   (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated access list: {access_list.name}",
    )
    db.add(audit_log)
    await db.commit()
    await db.refresh(access_list)

    return access_list


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_access_list(
    list_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete access list"""
    result = await db.execute(select(AccessList).where(AccessList.id == list_id))
    access_list = result.scalar_one_or_none()

    if not access_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access list not found",
        )

    # Audit log
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="access_list_deleted",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or
                   (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted access list: {access_list.name}",
    )
    db.add(audit_log)

    await db.delete(access_list)
    await db.commit()


# Entry management
@router.post("/{list_id}/entries", response_model=AccessListEntryResponse, status_code=status.HTTP_201_CREATED)
async def add_entry(
    list_id: str,
    entry_data: AccessListEntryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add entry to access list"""
    result = await db.execute(select(AccessList).where(AccessList.id == list_id))
    access_list = result.scalar_one_or_none()

    if not access_list:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Access list not found",
        )

    entry = AccessListEntry(
        access_list_id=list_id,
        **entry_data.model_dump()
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return entry


@router.delete("/{list_id}/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_entry(
    list_id: str,
    entry_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove entry from access list"""
    result = await db.execute(
        select(AccessListEntry).where(
            (AccessListEntry.id == entry_id) &
            (AccessListEntry.access_list_id == list_id)
        )
    )
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found",
        )

    await db.delete(entry)
    await db.commit()
