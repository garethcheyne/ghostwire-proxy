"""Threat detection and response service."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.waf import ThreatEvent, ThreatActor, ThreatThreshold
from app.models.firewall import FirewallBlocklist

logger = logging.getLogger(__name__)


def _send_push_notification_background(coro):
    """Fire and forget a push notification (don't block the main flow)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(coro)
        else:
            loop.run_until_complete(coro)
    except Exception as e:
        logger.debug(f"Could not send push notification: {e}")

# Severity score mapping
SEVERITY_SCORES = {
    "low": 10,
    "medium": 25,
    "high": 50,
    "critical": 100,
}


async def record_threat_event(
    db: AsyncSession,
    client_ip: str,
    category: str,
    severity: str,
    action_taken: str,
    request_method: Optional[str] = None,
    request_uri: Optional[str] = None,
    request_headers: Optional[str] = None,
    matched_payload: Optional[str] = None,
    user_agent: Optional[str] = None,
    host: Optional[str] = None,
    proxy_host_id: Optional[str] = None,
    rule_id: Optional[str] = None,
    rule_name: Optional[str] = None,
) -> ThreatEvent:
    """Record a threat event and update the threat actor profile."""
    # Create event
    event = ThreatEvent(
        proxy_host_id=proxy_host_id,
        client_ip=client_ip,
        rule_id=rule_id,
        rule_name=rule_name,
        category=category,
        severity=severity,
        action_taken=action_taken,
        request_method=request_method,
        request_uri=request_uri,
        request_headers=request_headers,
        matched_payload=matched_payload,
        user_agent=user_agent,
        host=host,
    )
    db.add(event)

    # Update or create threat actor
    result = await db.execute(
        select(ThreatActor).where(ThreatActor.ip_address == client_ip)
    )
    actor = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    score_delta = SEVERITY_SCORES.get(severity, 25)

    if actor:
        actor.total_events = (actor.total_events or 0) + 1
        actor.threat_score = (actor.threat_score or 0) + score_delta
        actor.last_seen = now
        actor.updated_at = now
    else:
        actor = ThreatActor(
            ip_address=client_ip,
            total_events=1,
            threat_score=score_delta,
            first_seen=now,
            last_seen=now,
        )
        db.add(actor)

    await db.flush()

    # Evaluate thresholds
    await evaluate_thresholds(db, actor)

    await db.commit()

    # Send push notification for high/critical severity threats
    if severity in ("high", "critical"):
        try:
            from app.services.push_service import push_service
            _send_push_notification_background(
                push_service.notify_threat_detected(
                    ip=client_ip,
                    threat_type=category,
                    severity=severity,
                    threat_id=event.id,
                )
            )
        except Exception as e:
            logger.debug(f"Push notification skipped: {e}")

    return event


async def evaluate_thresholds(db: AsyncSession, actor: ThreatActor) -> None:
    """Evaluate threat thresholds and escalate response if needed."""
    result = await db.execute(
        select(ThreatThreshold)
        .where(ThreatThreshold.enabled == True)
        .order_by(ThreatThreshold.priority.desc())
    )
    thresholds = result.scalars().all()

    now = datetime.now(timezone.utc)

    for threshold in thresholds:
        triggered = False

        # Check by threat score
        if threshold.threat_score and actor.threat_score >= threshold.threat_score:
            triggered = True

        # Check by event count within time window
        if threshold.events_count and threshold.time_window_minutes:
            window_start = now - timedelta(minutes=threshold.time_window_minutes)
            count_result = await db.execute(
                select(func.count(ThreatEvent.id)).where(
                    and_(
                        ThreatEvent.client_ip == actor.ip_address,
                        ThreatEvent.timestamp >= window_start,
                    )
                )
            )
            event_count = count_result.scalar() or 0
            if event_count >= threshold.events_count:
                triggered = True

        if triggered:
            await apply_response(db, actor, threshold.response_action, threshold.temp_block_duration_minutes)
            break  # Only apply the highest priority threshold


async def apply_response(
    db: AsyncSession,
    actor: ThreatActor,
    action: str,
    temp_block_minutes: Optional[int] = None,
) -> None:
    """Apply a threat response action to an actor."""
    now = datetime.now(timezone.utc)

    # Only escalate, never downgrade
    status_levels = {
        "monitored": 0,
        "warned": 1,
        "temp_blocked": 2,
        "perm_blocked": 3,
        "firewall_banned": 4,
    }
    current_level = status_levels.get(actor.current_status, 0)

    if action == "warn" and current_level < 1:
        actor.current_status = "warned"
        actor.updated_at = now
    elif action == "temp_block" and current_level < 2:
        actor.current_status = "temp_blocked"
        actor.temp_block_until = now + timedelta(minutes=temp_block_minutes or 60)
        actor.updated_at = now
    elif action == "perm_block" and current_level < 3:
        actor.current_status = "perm_blocked"
        actor.perm_blocked_at = now
        actor.updated_at = now
    elif action == "firewall_ban" and current_level < 4:
        actor.current_status = "firewall_banned"
        actor.firewall_banned_at = now
        actor.updated_at = now

        # Add to firewall blocklist
        blocklist_entry = FirewallBlocklist(
            threat_actor_id=actor.id,
            ip_address=actor.ip_address,
            status="pending",
        )
        db.add(blocklist_entry)

    logger.info(f"Threat response: {action} applied to {actor.ip_address} (score: {actor.threat_score})")

    # Send push notification for blocks
    if action in ("temp_block", "perm_block", "firewall_ban"):
        try:
            from app.services.push_service import push_service

            if action == "temp_block":
                duration = f"{temp_block_minutes} minutes" if temp_block_minutes else "1 hour"
            elif action == "perm_block":
                duration = "permanent"
            else:
                duration = "firewall ban"

            _send_push_notification_background(
                push_service.notify_ip_blocked(
                    ip=actor.ip_address,
                    reason=f"Threat score: {actor.threat_score}",
                    duration=duration,
                )
            )
        except Exception as e:
            logger.debug(f"Push notification skipped: {e}")


async def check_ip_blocked(db: AsyncSession, ip_address: str) -> tuple[bool, Optional[str]]:
    """Check if an IP is currently blocked. Returns (is_blocked, reason)."""
    result = await db.execute(
        select(ThreatActor).where(ThreatActor.ip_address == ip_address)
    )
    actor = result.scalar_one_or_none()

    if not actor:
        return False, None

    now = datetime.now(timezone.utc)

    if actor.current_status == "perm_blocked":
        return True, "permanently blocked"
    elif actor.current_status == "firewall_banned":
        return True, "firewall banned"
    elif actor.current_status == "temp_blocked":
        if actor.temp_block_until and actor.temp_block_until > now:
            return True, f"temporarily blocked until {actor.temp_block_until.isoformat()}"
        else:
            # Block expired, reset to warned
            actor.current_status = "warned"
            actor.temp_block_until = None
            actor.updated_at = now
            await db.commit()
            return False, None

    return False, None
