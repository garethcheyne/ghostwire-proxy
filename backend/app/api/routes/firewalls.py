"""Firewall connector API routes."""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.user import User
from app.models.firewall import FirewallConnector, FirewallBlocklist
from app.models.audit_log import AuditLog
from app.schemas.firewall import (
    FirewallConnectorCreate, FirewallConnectorUpdate, FirewallConnectorResponse,
    FirewallBlocklistResponse,
)
from app.api.deps import get_current_user
from app.services.firewall_service import get_connector as get_firewall_connector

router = APIRouter()


@router.get("", response_model=list[FirewallConnectorResponse])
async def list_connectors(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(FirewallConnector).order_by(FirewallConnector.name))
    return result.scalars().all()


@router.post("", response_model=FirewallConnectorResponse, status_code=status.HTTP_201_CREATED)
async def create_connector(
    data: FirewallConnectorCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.security import encrypt_data

    connector = FirewallConnector(
        name=data.name,
        connector_type=data.connector_type,
        host=data.host,
        port=data.port,
        username=data.username,
        password=encrypt_data(data.password) if data.password else None,
        api_key=encrypt_data(data.api_key) if data.api_key else None,
        site_id=data.site_id,
        address_list_name=data.address_list_name,
        enabled=data.enabled,
    )
    db.add(connector)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="firewall_connector_created",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Created firewall connector: {data.name} ({data.connector_type})",
    ))
    await db.commit()
    await db.refresh(connector)
    return connector


@router.get("/{connector_id}", response_model=FirewallConnectorResponse)
async def get_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(FirewallConnector).where(FirewallConnector.id == connector_id))
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(status_code=404, detail="Firewall connector not found")
    return connector


@router.put("/{connector_id}", response_model=FirewallConnectorResponse)
async def update_connector(
    connector_id: str,
    data: FirewallConnectorUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.core.security import encrypt_data

    result = await db.execute(select(FirewallConnector).where(FirewallConnector.id == connector_id))
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(status_code=404, detail="Firewall connector not found")

    update_data = data.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        update_data["password"] = encrypt_data(update_data["password"])
    if "api_key" in update_data and update_data["api_key"]:
        update_data["api_key"] = encrypt_data(update_data["api_key"])

    for field, value in update_data.items():
        setattr(connector, field, value)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="firewall_connector_updated",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated firewall connector: {connector.name}",
    ))
    await db.commit()
    await db.refresh(connector)
    return connector


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(
    connector_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(FirewallConnector).where(FirewallConnector.id == connector_id))
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(status_code=404, detail="Firewall connector not found")

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="firewall_connector_deleted",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted firewall connector: {connector.name}",
    ))
    await db.delete(connector)
    await db.commit()


@router.post("/{connector_id}/test")
async def test_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(FirewallConnector).where(FirewallConnector.id == connector_id))
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(status_code=404, detail="Firewall connector not found")

    instance = get_firewall_connector(connector)
    test_result = await instance.test_connection()
    return test_result


@router.post("/{connector_id}/test-block")
async def test_block(
    connector_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test adding and removing a block - uses a safe test IP (192.0.2.1 from TEST-NET-1)."""
    result = await db.execute(select(FirewallConnector).where(FirewallConnector.id == connector_id))
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(status_code=404, detail="Firewall connector not found")

    instance = get_firewall_connector(connector)
    test_ip = "192.0.2.1"  # TEST-NET-1 (RFC 5737) - safe for testing

    # Step 1: Add the test block
    add_result = await instance.add_to_blocklist(test_ip, "Ghostwire test block - will be removed")
    if not add_result:
        return {
            "success": False,
            "step": "add",
            "error": f"Failed to add {test_ip} to blocklist"
        }

    # Step 2: Remove the test block
    remove_result = await instance.remove_from_blocklist(test_ip)
    if not remove_result:
        return {
            "success": False,
            "step": "remove",
            "error": f"Added {test_ip} but failed to remove it - please remove manually"
        }

    # Log the test
    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="firewall_test_block",
        ip_address=request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else None),
        user_agent=request.headers.get("user-agent"),
        details=f"Tested block/unblock on {connector.name} with IP {test_ip}",
    ))
    await db.commit()

    return {
        "success": True,
        "message": f"Successfully added and removed {test_ip} from {connector.name}"
    }


@router.post("/{connector_id}/sync")
async def sync_blocklist(
    connector_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(FirewallConnector).where(FirewallConnector.id == connector_id))
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(status_code=404, detail="Firewall connector not found")

    # Get pending blocklist entries for this connector (or unassigned)
    bl_result = await db.execute(
        select(FirewallBlocklist).where(
            FirewallBlocklist.status == "pending",
            (FirewallBlocklist.connector_id == connector_id) | (FirewallBlocklist.connector_id == None),
        )
    )
    entries = bl_result.scalars().all()

    instance = get_firewall_connector(connector)
    pushed = 0
    errors = 0

    from datetime import datetime, timezone
    for entry in entries:
        success = await instance.add_to_blocklist(entry.ip_address, f"Ghostwire threat score block")
        if success:
            entry.status = "pushed"
            entry.pushed_at = datetime.now(timezone.utc)
            entry.connector_id = connector_id
            pushed += 1
        else:
            entry.error_message = "Push failed"
            errors += 1

    connector.last_sync_at = datetime.now(timezone.utc)
    await db.commit()

    return {"pushed": pushed, "errors": errors, "total": len(entries)}


@router.get("/blocklist/all", response_model=list[FirewallBlocklistResponse])
async def list_blocklist(
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(FirewallBlocklist).order_by(FirewallBlocklist.pushed_at.desc())
    if status_filter:
        query = query.where(FirewallBlocklist.status == status_filter)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()
