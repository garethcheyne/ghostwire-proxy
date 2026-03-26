"""Firewall connector API routes."""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.utils import get_client_ip
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


@router.get("/status")
async def firewall_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if any enabled firewall connectors are configured."""
    result = await db.execute(
        select(func.count(FirewallConnector.id)).where(FirewallConnector.enabled == True)
    )
    count = result.scalar() or 0
    return {"has_enabled_connectors": count > 0, "enabled_count": count}


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
        ip_address=get_client_ip(request),
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
        ip_address=get_client_ip(request),
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
        ip_address=get_client_ip(request),
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


@router.post("/{connector_id}/ensure-rule")
async def ensure_firewall_rule(
    connector_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ensure the firewall rule exists that enforces blocking for the IP group.

    For UniFi: Creates a WAN_IN drop rule using the ghostwire-blocked IP group.
    This makes the blocklist actually block traffic at the router level.
    """
    result = await db.execute(select(FirewallConnector).where(FirewallConnector.id == connector_id))
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(status_code=404, detail="Firewall connector not found")

    instance = get_firewall_connector(connector)

    # Check if this connector type supports ensure_firewall_rule
    if not hasattr(instance, 'ensure_firewall_rule'):
        return {
            "success": False,
            "error": f"Connector type '{connector.connector_type}' does not support automatic rule creation"
        }

    rule_result = await instance.ensure_firewall_rule()

    if rule_result.get("success"):
        db.add(AuditLog(
            user_id=current_user.id, email=current_user.email,
            action="firewall_rule_ensured",
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            details=f"Ensured firewall rule for {connector.name}: {rule_result.get('message', '')}",
        ))
        await db.commit()

    return rule_result


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
        ip_address=get_client_ip(request),
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

    instance = get_firewall_connector(connector)

    # Ensure firewall rule exists before syncing (for connectors that support it)
    rule_status = None
    if hasattr(instance, 'ensure_firewall_rule'):
        rule_result = await instance.ensure_firewall_rule()
        rule_status = "created" if rule_result.get("success") else f"failed: {rule_result.get('error', 'unknown')}"

    # Get pending blocklist entries for this connector (or unassigned)
    bl_result = await db.execute(
        select(FirewallBlocklist).where(
            FirewallBlocklist.status == "pending",
            (FirewallBlocklist.connector_id == connector_id) | (FirewallBlocklist.connector_id == None),
        )
    )
    entries = bl_result.scalars().all()

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

    return {
        "pushed": pushed,
        "errors": errors,
        "total": len(entries),
        "firewall_rule": rule_status,
    }


@router.get("/blocklist/all", response_model=list[FirewallBlocklistResponse])
async def list_blocklist(
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Deduplicate: for each ip_address, keep only the most recent entry
    # Subquery to find the max id (newest) per IP
    subq = (
        select(func.max(FirewallBlocklist.id).label("keep_id"))
        .group_by(FirewallBlocklist.ip_address)
    )
    if status_filter:
        subq = subq.where(FirewallBlocklist.status == status_filter)
    subq = subq.subquery()

    query = (
        select(FirewallBlocklist)
        .where(FirewallBlocklist.id.in_(select(subq.c.keep_id)))
        .order_by(FirewallBlocklist.pushed_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/blocklist/deduplicate")
async def deduplicate_blocklist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove duplicate IP entries from the blocklist, keeping the newest entry per IP."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    # Find IPs with more than one entry
    dup_query = (
        select(FirewallBlocklist.ip_address, func.count(FirewallBlocklist.id).label("cnt"))
        .group_by(FirewallBlocklist.ip_address)
        .having(func.count(FirewallBlocklist.id) > 1)
    )
    dup_result = await db.execute(dup_query)
    dup_ips = [row.ip_address for row in dup_result.all()]

    removed = 0
    for ip in dup_ips:
        # Get all entries for this IP, ordered newest first
        entries_result = await db.execute(
            select(FirewallBlocklist)
            .where(FirewallBlocklist.ip_address == ip)
            .order_by(FirewallBlocklist.pushed_at.desc().nullslast(), FirewallBlocklist.id.desc())
        )
        entries = entries_result.scalars().all()
        # Keep the first (newest), delete the rest
        for entry in entries[1:]:
            await db.delete(entry)
            removed += 1

    await db.commit()
    return {"removed": removed, "duplicate_ips": len(dup_ips)}
