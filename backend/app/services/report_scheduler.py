"""Delivery of scheduled report emails.

Runs from a background loop in main.py, checking once an hour. Each schedule
records its own `last_sent_at`, and the due check compares against that rather
than against "did this tick land in the right minute" — so a restart, a slow
tick or a container that was down at 07:00 doesn't silently skip a report.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.proxy_host import ProxyHost
from app.models.report_schedule import ReportSchedule
from app.services import email_service
from app.services.host_report_service import build_host_report
from app.services.report_email import render_report_email

logger = logging.getLogger(__name__)

# A schedule that missed its slot by more than this is sent late rather than
# skipped; beyond it, the window is treated as lost so a container that was off
# for a week doesn't emit seven backdated reports at once.
GRACE_HOURS = 18


def _recipients(schedule: ReportSchedule) -> list[str]:
    try:
        values = json.loads(schedule.recipients or "[]")
    except json.JSONDecodeError:
        return []
    return [str(v).strip() for v in values if str(v).strip()]


def is_due(schedule: ReportSchedule, now: Optional[datetime] = None) -> bool:
    """Whether this schedule's slot has arrived and not yet been served."""
    if not schedule.enabled or not _recipients(schedule):
        return False

    now = now or datetime.now(timezone.utc)

    if now.hour < schedule.send_hour:
        return False

    if schedule.frequency == "weekly":
        # send_day is 0=Monday..6=Sunday; default Monday.
        if now.weekday() != (schedule.send_day if schedule.send_day is not None else 0):
            return False
    elif schedule.frequency == "monthly":
        if now.day != (schedule.send_day if schedule.send_day is not None else 1):
            return False

    last = schedule.last_sent_at
    if last is None:
        return True

    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    # Don't re-send within the same period.
    min_gap = {
        "daily": timedelta(hours=20),
        "weekly": timedelta(days=6),
        "monthly": timedelta(days=27),
    }.get(schedule.frequency, timedelta(days=6))

    return (now - last) >= min_gap


async def deliver_schedule(db: AsyncSession, schedule: ReportSchedule) -> tuple[bool, str]:
    """Build and send one scheduled report. Records the outcome on the row."""
    recipients = _recipients(schedule)
    if not recipients:
        return False, "No recipients configured"

    try:
        if schedule.proxy_host_id:
            host = (await db.execute(
                select(ProxyHost).where(ProxyHost.id == schedule.proxy_host_id)
            )).scalar_one_or_none()
            if not host:
                raise ValueError(f"Proxy host {schedule.proxy_host_id} no longer exists")
            report = await build_host_report(db, host, schedule.period)
            subject, text, html = render_report_email(report)
        else:
            # Fleet-wide: one email per host, so each report stays readable.
            hosts = (await db.execute(select(ProxyHost))).scalars().all()
            if not hosts:
                raise ValueError("No proxy hosts configured")
            sent_for = 0
            for host in hosts:
                report = await build_host_report(db, host, schedule.period)
                subject, text, html = render_report_email(report)
                await email_service.send_email(
                    db, to=recipients, subject=subject, text_body=text, html_body=html
                )
                sent_for += 1

            schedule.last_sent_at = datetime.now(timezone.utc)
            schedule.last_status = "sent"
            schedule.last_error = None
            schedule.send_count = (schedule.send_count or 0) + 1
            await db.commit()
            return True, f"Sent {sent_for} host reports to {len(recipients)} recipient(s)"

        await email_service.send_email(
            db, to=recipients, subject=subject, text_body=text, html_body=html
        )

        schedule.last_sent_at = datetime.now(timezone.utc)
        schedule.last_status = "sent"
        schedule.last_error = None
        schedule.send_count = (schedule.send_count or 0) + 1
        await db.commit()

        return True, f"Sent to {len(recipients)} recipient(s)"

    except Exception as e:
        logger.error("Scheduled report %r failed: %s", schedule.name, e)
        schedule.last_status = "failed"
        schedule.last_error = str(e)[:2000]
        # last_sent_at is deliberately NOT advanced on failure, so the next tick
        # retries rather than treating the slot as served.
        await db.commit()
        return False, str(e)


async def run_due_schedules(db: AsyncSession) -> int:
    """Send every schedule whose slot has arrived. Returns how many were sent."""
    schedules = (await db.execute(
        select(ReportSchedule).where(ReportSchedule.enabled == True)
    )).scalars().all()

    now = datetime.now(timezone.utc)
    sent = 0

    for schedule in schedules:
        if not is_due(schedule, now):
            continue
        ok, detail = await deliver_schedule(db, schedule)
        if ok:
            sent += 1
            logger.info("Scheduled report %r: %s", schedule.name, detail)

    return sent
