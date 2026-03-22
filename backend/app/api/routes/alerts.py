"""Alert channels, preferences, and push notification API routes."""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.core.utils import get_client_ip
from app.models.user import User
from app.models.alert import PushSubscription, AlertChannel, AlertPreference
from app.models.audit_log import AuditLog
from app.schemas.alert import (
    PushSubscriptionCreate, PushSubscriptionResponse,
    AlertChannelCreate, AlertChannelUpdate, AlertChannelResponse,
    AlertPreferenceCreate, AlertPreferenceUpdate, AlertPreferenceResponse,
)
from app.api.deps import get_current_user
from app.services.alert_service import dispatch_alert
from app.services.push_service import push_service

router = APIRouter()


# ── VAPID Key ─────────────────────────────────────────────────

@router.get("/push/vapid-key")
async def get_vapid_public_key():
    """Get the VAPID public key for push notification subscription."""
    if not settings.vapid_public_key:
        raise HTTPException(
            status_code=503,
            detail="Push notifications not configured. VAPID keys not set."
        )
    return {
        "public_key": settings.vapid_public_key,
        "configured": push_service.is_configured(),
    }


# ── Push Subscriptions ─────────────────────────────────────────

@router.post("/push/subscribe", response_model=PushSubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def subscribe_push(
    data: PushSubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Remove existing subscription with same endpoint
    result = await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == data.endpoint)
    )
    existing = result.scalar_one_or_none()
    if existing:
        await db.delete(existing)

    sub = PushSubscription(
        user_id=current_user.id,
        endpoint=data.endpoint,
        p256dh_key=data.p256dh_key,
        auth_key=data.auth_key,
        user_agent=data.user_agent,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


@router.delete("/push/unsubscribe")
async def unsubscribe_push(
    endpoint: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == current_user.id,
            PushSubscription.endpoint == endpoint,
        )
    )
    sub = result.scalar_one_or_none()
    if sub:
        await db.delete(sub)
        await db.commit()
    return {"status": "unsubscribed"}


# ── Alert Channels ─────────────────────────────────────────────

@router.get("/channels", response_model=list[AlertChannelResponse])
async def list_channels(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AlertChannel).where(
            (AlertChannel.user_id == current_user.id) | (AlertChannel.user_id == None)
        ).order_by(AlertChannel.name)
    )
    return result.scalars().all()


@router.post("/channels", response_model=AlertChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    data: AlertChannelCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    channel = AlertChannel(
        user_id=current_user.id,
        channel_type=data.channel_type,
        name=data.name,
        config=data.config,
        enabled=data.enabled,
    )
    db.add(channel)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="alert_channel_created",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Created alert channel: {data.name} ({data.channel_type})",
    ))
    await db.commit()
    await db.refresh(channel)
    return channel


@router.put("/channels/{channel_id}", response_model=AlertChannelResponse)
async def update_channel(
    channel_id: str,
    data: AlertChannelUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AlertChannel).where(AlertChannel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Alert channel not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(channel, field, value)

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="alert_channel_updated",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Updated alert channel: {channel.name}",
    ))
    await db.commit()
    await db.refresh(channel)
    return channel


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AlertChannel).where(AlertChannel.id == channel_id))
    channel = result.scalar_one_or_none()
    if not channel:
        raise HTTPException(status_code=404, detail="Alert channel not found")

    db.add(AuditLog(
        user_id=current_user.id, email=current_user.email,
        action="alert_channel_deleted",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=f"Deleted alert channel: {channel.name}",
    ))
    await db.delete(channel)
    await db.commit()


# ── Alert Preferences ─────────────────────────────────────────

@router.get("/preferences", response_model=list[AlertPreferenceResponse])
async def list_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AlertPreference).where(AlertPreference.user_id == current_user.id)
    )
    return result.scalars().all()


@router.post("/preferences", response_model=AlertPreferenceResponse, status_code=status.HTTP_201_CREATED)
async def create_preference(
    data: AlertPreferenceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Check for duplicate
    result = await db.execute(
        select(AlertPreference).where(
            AlertPreference.user_id == current_user.id,
            AlertPreference.alert_type == data.alert_type,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Preference for this alert type already exists")

    pref = AlertPreference(
        user_id=current_user.id,
        alert_type=data.alert_type,
        min_severity=data.min_severity,
        channels=data.channels,
        enabled=data.enabled,
    )
    db.add(pref)
    await db.commit()
    await db.refresh(pref)
    return pref


@router.put("/preferences/{pref_id}", response_model=AlertPreferenceResponse)
async def update_preference(
    pref_id: str,
    data: AlertPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AlertPreference).where(
            AlertPreference.id == pref_id,
            AlertPreference.user_id == current_user.id,
        )
    )
    pref = result.scalar_one_or_none()
    if not pref:
        raise HTTPException(status_code=404, detail="Alert preference not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(pref, field, value)

    await db.commit()
    await db.refresh(pref)
    return pref


@router.delete("/preferences/{pref_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preference(
    pref_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AlertPreference).where(
            AlertPreference.id == pref_id,
            AlertPreference.user_id == current_user.id,
        )
    )
    pref = result.scalar_one_or_none()
    if not pref:
        raise HTTPException(status_code=404, detail="Alert preference not found")

    await db.delete(pref)
    await db.commit()


# ── Test Alert ─────────────────────────────────────────────────

@router.post("/test")
async def send_test_alert(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a test alert via all configured channels."""
    result = await dispatch_alert(
        db=db,
        alert_type="threat_detected",
        severity="medium",
        title="Test Alert",
        message="This is a test alert from Ghostwire Proxy.",
        data={"test": True},
    )
    return {"status": "sent", **result}


@router.post("/push/test")
async def send_test_push(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a test push notification directly to all subscriptions."""
    if not push_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Push notifications not configured. VAPID keys not set."
        )

    result = await push_service.notify_all(
        title="Test Notification",
        body="Push notifications are working correctly!",
        notification_type="test",
        data={"test": True},
        db=db,
    )
    return {"status": "sent", **result}


@router.get("/push/subscriptions")
async def list_my_subscriptions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List current user's push subscriptions."""
    result = await db.execute(
        select(PushSubscription).where(PushSubscription.user_id == current_user.id)
    )
    subs = result.scalars().all()
    return [
        {
            "id": sub.id,
            "endpoint": sub.endpoint[:50] + "..." if len(sub.endpoint) > 50 else sub.endpoint,
            "user_agent": sub.user_agent,
            "created_at": sub.created_at.isoformat() if sub.created_at else None,
        }
        for sub in subs
    ]
