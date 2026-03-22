"""
Simple Push Notification Service

Easy-to-use interface for sending Web Push notifications.

Usage:
    from app.services.push_service import push_service

    # Send to all users
    await push_service.notify_all(
        title="Security Alert",
        body="Threat detected from IP 1.2.3.4",
        notification_type="threat",
        data={"threat_id": "abc123", "ip": "1.2.3.4"}
    )

    # Send to specific user
    await push_service.notify_user(
        user_id="user-uuid",
        title="Update Available",
        body="Version 1.1.0 is ready to install",
        notification_type="update"
    )

    # Pre-built notification types
    await push_service.notify_threat_detected(ip="1.2.3.4", threat_type="SQL Injection")
    await push_service.notify_update_available(version="1.1.0")
    await push_service.notify_certificate_expiring(domain="example.com", days=7)
    await push_service.notify_under_attack(attack_type="DDoS", requests_per_minute=10000)
"""

import json
import logging
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.alert import PushSubscription

logger = logging.getLogger(__name__)


class PushService:
    """Service for sending Web Push notifications."""

    def __init__(self):
        self._webpush = None

    @property
    def webpush(self):
        """Lazy load webpush to avoid import errors if not installed."""
        if self._webpush is None:
            try:
                from pywebpush import webpush
                self._webpush = webpush
            except ImportError:
                logger.warning("pywebpush not installed - push notifications disabled")
        return self._webpush

    def is_configured(self) -> bool:
        """Check if VAPID keys are configured."""
        return bool(settings.vapid_public_key and settings.vapid_private_key)

    async def _get_subscriptions(
        self,
        db: AsyncSession,
        user_id: Optional[str] = None
    ) -> List[PushSubscription]:
        """Get push subscriptions from database."""
        query = select(PushSubscription)
        if user_id:
            query = query.where(PushSubscription.user_id == user_id)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def _send_to_subscription(
        self,
        subscription: PushSubscription,
        payload: dict
    ) -> bool:
        """Send notification to a single subscription."""
        if not self.webpush or not self.is_configured():
            return False

        try:
            from pywebpush import WebPushException

            self.webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {
                        "p256dh": subscription.p256dh_key,
                        "auth": subscription.auth_key,
                    },
                },
                data=json.dumps(payload),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_email},
            )
            return True

        except Exception as e:
            error_str = str(e)
            # 410 Gone or 404 Not Found = subscription expired
            if "410" in error_str or "404" in error_str:
                logger.info(f"Subscription expired: {subscription.id}")
                # Mark for cleanup (don't delete here to avoid session issues)
            else:
                logger.error(f"Push failed: {e}")
            return False

    async def notify_all(
        self,
        title: str,
        body: str,
        notification_type: str = "general",
        data: Optional[dict] = None,
        actions: Optional[List[dict]] = None,
        require_interaction: bool = False,
        db: Optional[AsyncSession] = None,
    ) -> dict:
        """
        Send notification to all subscribed users.

        Args:
            title: Notification title
            body: Notification body text
            notification_type: Type for routing (threat, update, certificate, backup, etc.)
            data: Additional data to include
            actions: Action buttons (e.g., [{"action": "view", "title": "View Details"}])
            require_interaction: Keep notification visible until user interacts
            db: Optional database session (creates one if not provided)

        Returns:
            {"sent": N, "failed": N, "total": N}
        """
        if not self.is_configured():
            logger.warning("VAPID keys not configured - skipping push notifications")
            return {"sent": 0, "failed": 0, "total": 0, "error": "VAPID keys not configured"}

        payload = {
            "title": title,
            "body": body,
            "icon": "/icons/icon-192x192.png",
            "badge": "/icons/icon-96x96.png",
            "tag": f"ghostwire-{notification_type}",
            "data": {
                "type": notification_type,
                **(data or {}),
            },
            "requireInteraction": require_interaction,
        }

        if actions:
            payload["actions"] = actions

        # Use provided session or create new one
        close_session = False
        if db is None:
            db = AsyncSessionLocal()
            close_session = True

        try:
            subscriptions = await self._get_subscriptions(db)
            sent = 0
            failed = 0

            for sub in subscriptions:
                if await self._send_to_subscription(sub, payload):
                    sent += 1
                else:
                    failed += 1

            return {"sent": sent, "failed": failed, "total": len(subscriptions)}

        finally:
            if close_session:
                await db.close()

    async def notify_user(
        self,
        user_id: str,
        title: str,
        body: str,
        notification_type: str = "general",
        data: Optional[dict] = None,
        db: Optional[AsyncSession] = None,
    ) -> dict:
        """Send notification to a specific user."""
        if not self.is_configured():
            return {"sent": 0, "failed": 0, "total": 0, "error": "VAPID keys not configured"}

        payload = {
            "title": title,
            "body": body,
            "icon": "/icons/icon-192x192.png",
            "badge": "/icons/icon-96x96.png",
            "tag": f"ghostwire-{notification_type}",
            "data": {
                "type": notification_type,
                **(data or {}),
            },
        }

        close_session = False
        if db is None:
            db = AsyncSessionLocal()
            close_session = True

        try:
            subscriptions = await self._get_subscriptions(db, user_id)
            sent = 0
            failed = 0

            for sub in subscriptions:
                if await self._send_to_subscription(sub, payload):
                    sent += 1
                else:
                    failed += 1

            return {"sent": sent, "failed": failed, "total": len(subscriptions)}

        finally:
            if close_session:
                await db.close()

    # =========================================================================
    # PRE-BUILT NOTIFICATION TYPES
    # =========================================================================

    async def notify_threat_detected(
        self,
        ip: str,
        threat_type: str,
        severity: str = "high",
        threat_id: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> dict:
        """Notify about a detected threat."""
        return await self.notify_all(
            title=f"Threat Detected - {severity.upper()}",
            body=f"{threat_type} from {ip}",
            notification_type="threat",
            data={
                "ip": ip,
                "threat_type": threat_type,
                "severity": severity,
                "threat_id": threat_id,
            },
            actions=[
                {"action": "view", "title": "View Details"},
                {"action": "block", "title": "Block IP"},
            ],
            require_interaction=severity in ["high", "critical"],
            db=db,
        )

    async def notify_under_attack(
        self,
        attack_type: str,
        requests_per_minute: int,
        source_ips: Optional[List[str]] = None,
        db: Optional[AsyncSession] = None,
    ) -> dict:
        """Notify about an ongoing attack."""
        return await self.notify_all(
            title="UNDER ATTACK",
            body=f"{attack_type} - {requests_per_minute:,} requests/min",
            notification_type="attack",
            data={
                "attack_type": attack_type,
                "requests_per_minute": requests_per_minute,
                "source_ips": source_ips,
            },
            actions=[
                {"action": "view", "title": "View Dashboard"},
            ],
            require_interaction=True,
            db=db,
        )

    async def notify_ip_blocked(
        self,
        ip: str,
        reason: str,
        duration: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> dict:
        """Notify about a blocked IP."""
        body = f"Blocked {ip}: {reason}"
        if duration:
            body += f" ({duration})"

        return await self.notify_all(
            title="IP Blocked",
            body=body,
            notification_type="firewall",
            data={"ip": ip, "reason": reason, "duration": duration},
            db=db,
        )

    async def notify_update_available(
        self,
        version: str,
        release_notes_url: Optional[str] = None,
        db: Optional[AsyncSession] = None,
    ) -> dict:
        """Notify about an available update."""
        return await self.notify_all(
            title="Update Available",
            body=f"Version {version} is ready to install",
            notification_type="update",
            data={
                "version": version,
                "url": "/dashboard/settings/updates",
                "release_notes_url": release_notes_url,
            },
            actions=[
                {"action": "update", "title": "Update Now"},
                {"action": "dismiss", "title": "Later"},
            ],
            db=db,
        )

    async def notify_update_completed(
        self,
        version: str,
        db: Optional[AsyncSession] = None,
    ) -> dict:
        """Notify about a completed update."""
        return await self.notify_all(
            title="Update Complete",
            body=f"Successfully updated to version {version}",
            notification_type="update",
            data={"version": version},
            db=db,
        )

    async def notify_certificate_expiring(
        self,
        domain: str,
        days: int,
        db: Optional[AsyncSession] = None,
    ) -> dict:
        """Notify about an expiring certificate."""
        return await self.notify_all(
            title="Certificate Expiring",
            body=f"{domain} expires in {days} days",
            notification_type="certificate",
            data={"domain": domain, "days": days},
            actions=[
                {"action": "view", "title": "View Certificates"},
            ],
            require_interaction=days <= 7,
            db=db,
        )

    async def notify_backup_completed(
        self,
        backup_id: str,
        size_mb: float,
        db: Optional[AsyncSession] = None,
    ) -> dict:
        """Notify about a completed backup."""
        return await self.notify_all(
            title="Backup Complete",
            body=f"Backup created ({size_mb:.1f} MB)",
            notification_type="backup",
            data={"backup_id": backup_id, "size_mb": size_mb},
            db=db,
        )

    async def notify_backup_failed(
        self,
        error: str,
        db: Optional[AsyncSession] = None,
    ) -> dict:
        """Notify about a failed backup."""
        return await self.notify_all(
            title="Backup Failed",
            body=error[:100],
            notification_type="backup",
            data={"error": error},
            require_interaction=True,
            db=db,
        )


# Global service instance
push_service = PushService()
