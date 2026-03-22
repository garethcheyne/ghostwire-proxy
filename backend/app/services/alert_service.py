"""Alert dispatch service for push notifications, email, webhooks."""

import logging
import json
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.alert import PushSubscription, AlertChannel, AlertPreference

logger = logging.getLogger(__name__)


async def dispatch_alert(
    db: AsyncSession,
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    data: Optional[dict] = None,
) -> dict:
    """Dispatch an alert to all configured channels based on user preferences."""
    severity_levels = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    severity_level = severity_levels.get(severity, 1)

    # Get all preferences matching this alert type
    result = await db.execute(
        select(AlertPreference).where(
            AlertPreference.alert_type == alert_type,
            AlertPreference.enabled == True,
        )
    )
    preferences = result.scalars().all()

    sent_count = 0
    error_count = 0

    for pref in preferences:
        # Check minimum severity
        min_level = severity_levels.get(pref.min_severity, 1)
        if severity_level < min_level:
            continue

        # Get channels for this preference
        channel_ids = json.loads(pref.channels) if pref.channels else []

        if not channel_ids:
            # Use all channels for this user
            ch_result = await db.execute(
                select(AlertChannel).where(
                    AlertChannel.user_id == pref.user_id,
                    AlertChannel.enabled == True,
                )
            )
            channels = ch_result.scalars().all()
        else:
            ch_result = await db.execute(
                select(AlertChannel).where(
                    AlertChannel.id.in_(channel_ids),
                    AlertChannel.enabled == True,
                )
            )
            channels = ch_result.scalars().all()

        for channel in channels:
            try:
                success = await _send_to_channel(db, channel, title, message, data)
                if success:
                    sent_count += 1
                else:
                    error_count += 1
            except Exception as e:
                logger.error(f"Failed to send alert to channel {channel.id}: {e}")
                error_count += 1

    return {"sent": sent_count, "errors": error_count}


async def _send_to_channel(
    db: AsyncSession,
    channel: AlertChannel,
    title: str,
    message: str,
    data: Optional[dict] = None,
) -> bool:
    """Send alert to a specific channel."""
    if channel.channel_type == "push":
        return await _send_push(db, channel, title, message, data)
    elif channel.channel_type == "webhook":
        return await _send_webhook(channel, title, message, data)
    elif channel.channel_type == "slack":
        return await _send_slack(channel, title, message, data)
    elif channel.channel_type == "telegram":
        return await _send_telegram(channel, title, message, data)
    elif channel.channel_type == "email":
        return await _send_email(channel, title, message, data)

    return False


async def _send_push(
    db: AsyncSession,
    channel: AlertChannel,
    title: str,
    message: str,
    data: Optional[dict] = None,
) -> bool:
    """Send Web Push notification."""
    try:
        from pywebpush import webpush, WebPushException

        result = await db.execute(
            select(PushSubscription).where(
                PushSubscription.user_id == channel.user_id
            )
        )
        subscriptions = result.scalars().all()

        payload = json.dumps({
            "title": title,
            "body": message,
            "data": data or {},
        })

        config = json.loads(channel.config) if channel.config else {}
        vapid_private_key = config.get("vapid_private_key", "")
        vapid_claims = config.get("vapid_claims", {"sub": "mailto:admin@ghostwire.local"})

        for sub in subscriptions:
            try:
                webpush(
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {
                            "p256dh": sub.p256dh_key,
                            "auth": sub.auth_key,
                        },
                    },
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims=vapid_claims,
                )
            except WebPushException as e:
                logger.warning(f"Push notification failed for subscription {sub.id}: {e}")
                if "410" in str(e) or "404" in str(e):
                    await db.delete(sub)

        return True
    except ImportError:
        logger.warning("pywebpush not installed, skipping push notifications")
        return False
    except Exception as e:
        logger.error(f"Push notification error: {e}")
        return False


async def _send_webhook(
    channel: AlertChannel,
    title: str,
    message: str,
    data: Optional[dict] = None,
) -> bool:
    """Send webhook notification."""
    try:
        import httpx

        config = json.loads(channel.config) if channel.config else {}
        url = config.get("url", "")

        if not url:
            return False

        payload = {
            "title": title,
            "message": message,
            "data": data or {},
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code < 400
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return False


async def _send_slack(
    channel: AlertChannel,
    title: str,
    message: str,
    data: Optional[dict] = None,
) -> bool:
    """Send Slack notification via webhook."""
    try:
        import httpx

        config = json.loads(channel.config) if channel.config else {}
        webhook_url = config.get("webhook_url", "")

        if not webhook_url:
            return False

        payload = {
            "text": f"*{title}*\n{message}",
        }

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Slack error: {e}")
        return False


async def _send_telegram(
    channel: AlertChannel,
    title: str,
    message: str,
    data: Optional[dict] = None,
) -> bool:
    """Send Telegram notification."""
    try:
        import httpx

        config = json.loads(channel.config) if channel.config else {}
        bot_token = config.get("bot_token", "")
        chat_id = config.get("chat_id", "")

        if not bot_token or not chat_id:
            return False

        text = f"<b>{title}</b>\n{message}"

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                },
            )
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


async def _send_email(
    channel: AlertChannel,
    title: str,
    message: str,
    data: Optional[dict] = None,
) -> bool:
    """Send email notification (placeholder - requires SMTP config)."""
    logger.info(f"Email alert: {title} - {message}")
    return True
