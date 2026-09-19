"""Per-host traffic reports and their email schedules."""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field, EmailStr
from typing import Optional

from app.core.cache import cached_json
from app.core.database import get_db
from app.models.proxy_host import ProxyHost
from app.models.report_schedule import ReportSchedule
from app.models.user import User
from app.api.deps import get_current_user
from app.services.host_report_service import build_host_report, PERIODS
from app.services.report_email import render_report_email
from app.services import email_service

logger = logging.getLogger(__name__)
router = APIRouter()


class ScheduleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    proxy_host_id: Optional[str] = None
    frequency: str = Field("weekly", pattern="^(daily|weekly|monthly)$")
    send_hour: int = Field(7, ge=0, le=23)
    send_day: Optional[int] = None
    period: str = Field("7d", pattern="^(24h|7d|30d|90d|365d)$")
    recipients: list[EmailStr]
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: Optional[str] = None
    proxy_host_id: Optional[str] = None
    frequency: Optional[str] = Field(None, pattern="^(daily|weekly|monthly)$")
    send_hour: Optional[int] = Field(None, ge=0, le=23)
    send_day: Optional[int] = None
    period: Optional[str] = Field(None, pattern="^(24h|7d|30d|90d|365d)$")
    recipients: Optional[list[EmailStr]] = None
    enabled: Optional[bool] = None


def _schedule_json(s: ReportSchedule) -> dict:
    try:
        recipients = json.loads(s.recipients or "[]")
    except json.JSONDecodeError:
        recipients = []
    return {
        "id": s.id,
        "name": s.name,
        "proxy_host_id": s.proxy_host_id,
        "frequency": s.frequency,
        "send_hour": s.send_hour,
        "send_day": s.send_day,
        "period": s.period,
        "recipients": recipients,
        "enabled": s.enabled,
        "last_sent_at": s.last_sent_at.isoformat() if s.last_sent_at else None,
        "last_status": s.last_status,
        "last_error": s.last_error,
        "send_count": s.send_count,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


async def _get_host(db: AsyncSession, host_id: str) -> ProxyHost:
    host = (await db.execute(select(ProxyHost).where(ProxyHost.id == host_id))).scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proxy host not found")
    return host


@router.get("/hosts/{host_id}")
async def get_host_report(
    host_id: str,
    period: str = Query("30d", pattern="^(24h|7d|30d|90d|365d)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full traffic, audience and security report for one host.

    Cached briefly — this runs a dozen aggregate queries, and a report page that
    several people open at once shouldn't run them each time.
    """
    host = await _get_host(db, host_id)

    ttl = {"24h": 60, "7d": 180, "30d": 300, "90d": 600, "365d": 900}.get(period, 300)

    async def _compute():
        return await build_host_report(db, host, period)

    return await cached_json(f"report:host:{host_id}:{period}", ttl=ttl, producer=_compute)


@router.get("/hosts/{host_id}/email-preview")
async def preview_host_report_email(
    host_id: str,
    period: str = Query("7d", pattern="^(24h|7d|30d|90d|365d)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The exact HTML a scheduled email would contain, for checking before sending."""
    host = await _get_host(db, host_id)
    report = await build_host_report(db, host, period)
    subject, text, html = render_report_email(report)
    return {"subject": subject, "text": text, "html": html}


@router.post("/hosts/{host_id}/send")
async def send_host_report_now(
    host_id: str,
    payload: dict,
    period: str = Query("7d", pattern="^(24h|7d|30d|90d|365d)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a host report by email immediately."""
    recipients = payload.get("recipients") or []
    if isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.split(",") if r.strip()]
    if not recipients:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No recipients specified")

    host = await _get_host(db, host_id)
    report = await build_host_report(db, host, period)
    subject, text, html = render_report_email(report)

    try:
        await email_service.send_email(db, to=recipients, subject=subject, text_body=text, html_body=html)
    except email_service.EmailNotConfigured as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Sending host report failed: %s", e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not send email: {e}")

    return {"sent": True, "recipients": recipients, "subject": subject}


# ── Schedules ───────────────────────────────────────────────────────────────

@router.get("/schedules")
async def list_schedules(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(ReportSchedule).order_by(ReportSchedule.created_at.desc()))).scalars().all()
    return [_schedule_json(s) for s in rows]


@router.post("/schedules", status_code=status.HTTP_201_CREATED)
async def create_schedule(
    payload: ScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.proxy_host_id:
        await _get_host(db, payload.proxy_host_id)

    schedule = ReportSchedule(
        name=payload.name,
        proxy_host_id=payload.proxy_host_id,
        frequency=payload.frequency,
        send_hour=payload.send_hour,
        send_day=payload.send_day,
        period=payload.period,
        recipients=json.dumps([str(r) for r in payload.recipients]),
        enabled=payload.enabled,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return _schedule_json(schedule)


@router.put("/schedules/{schedule_id}")
async def update_schedule(
    schedule_id: str,
    payload: ScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    schedule = (await db.execute(
        select(ReportSchedule).where(ReportSchedule.id == schedule_id)
    )).scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    data = payload.model_dump(exclude_unset=True)
    if "recipients" in data and data["recipients"] is not None:
        data["recipients"] = json.dumps([str(r) for r in data["recipients"]])

    for key, value in data.items():
        setattr(schedule, key, value)

    await db.commit()
    await db.refresh(schedule)
    return _schedule_json(schedule)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    schedule = (await db.execute(
        select(ReportSchedule).where(ReportSchedule.id == schedule_id)
    )).scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    await db.delete(schedule)
    await db.commit()


@router.post("/schedules/{schedule_id}/run")
async def run_schedule_now(
    schedule_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a scheduled report immediately, without waiting for its next slot."""
    from app.services.report_scheduler import deliver_schedule

    schedule = (await db.execute(
        select(ReportSchedule).where(ReportSchedule.id == schedule_id)
    )).scalar_one_or_none()
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")

    ok, detail = await deliver_schedule(db, schedule)
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail)
    return {"sent": True, "detail": detail}


# ── SMTP configuration ──────────────────────────────────────────────────────

@router.get("/smtp")
async def get_smtp(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await email_service.get_smtp_config(db)


@router.put("/smtp")
async def put_smtp(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await email_service.save_smtp_config(db, payload)


@router.post("/smtp/test")
async def test_smtp(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    to = (payload.get("to") or "").strip()
    if not to:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No test recipient specified")

    try:
        await email_service.send_test_email(db, to)
    except email_service.EmailNotConfigured as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not send test email: {e}")

    return {"sent": True, "to": to}
