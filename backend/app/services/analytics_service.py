"""Analytics aggregation service."""

import logging
import json
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
import uuid

from app.models.traffic_log import TrafficLog
from app.models.waf import ThreatEvent
from app.models.analytics import AnalyticsHourly, AnalyticsDaily, AnalyticsGeo

logger = logging.getLogger(__name__)


async def aggregate_hourly(db: AsyncSession, hours_back: int = 2) -> int:
    """Aggregate traffic logs into hourly buckets."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours_back)

    # Get distinct hours with traffic
    result = await db.execute(
        select(
            TrafficLog.proxy_host_id,
            func.strftime('%Y-%m-%dT%H:00:00', TrafficLog.timestamp).label('hour'),
            func.count(TrafficLog.id).label('total_requests'),
            func.sum(TrafficLog.bytes_sent).label('bytes_sent'),
            func.sum(TrafficLog.bytes_received).label('bytes_received'),
            func.avg(TrafficLog.response_time).label('avg_response_time'),
            func.count(func.nullif(TrafficLog.status < 300, False)).label('status_2xx'),
            func.count(func.nullif(and_(TrafficLog.status >= 300, TrafficLog.status < 400), False)).label('status_3xx'),
            func.count(func.nullif(and_(TrafficLog.status >= 400, TrafficLog.status < 500), False)).label('status_4xx'),
            func.count(func.nullif(TrafficLog.status >= 500, False)).label('status_5xx'),
            func.count(func.distinct(TrafficLog.client_ip)).label('unique_ips'),
        )
        .where(TrafficLog.timestamp >= start)
        .group_by(
            TrafficLog.proxy_host_id,
            func.strftime('%Y-%m-%dT%H:00:00', TrafficLog.timestamp),
        )
    )
    rows = result.all()

    count = 0
    for row in rows:
        # Upsert hourly record
        existing = await db.execute(
            select(AnalyticsHourly).where(
                and_(
                    AnalyticsHourly.proxy_host_id == row.proxy_host_id,
                    AnalyticsHourly.hour == row.hour,
                )
            )
        )
        hourly = existing.scalar_one_or_none()

        if hourly:
            hourly.total_requests = row.total_requests or 0
            hourly.bytes_sent = row.bytes_sent or 0
            hourly.bytes_received = row.bytes_received or 0
            hourly.avg_response_time_ms = int(row.avg_response_time) if row.avg_response_time else None
            hourly.status_2xx = row.status_2xx or 0
            hourly.status_3xx = row.status_3xx or 0
            hourly.status_4xx = row.status_4xx or 0
            hourly.status_5xx = row.status_5xx or 0
            hourly.unique_ips = row.unique_ips or 0
        else:
            hourly = AnalyticsHourly(
                id=str(uuid.uuid4()),
                proxy_host_id=row.proxy_host_id,
                hour=row.hour,
                total_requests=row.total_requests or 0,
                bytes_sent=row.bytes_sent or 0,
                bytes_received=row.bytes_received or 0,
                avg_response_time_ms=int(row.avg_response_time) if row.avg_response_time else None,
                status_2xx=row.status_2xx or 0,
                status_3xx=row.status_3xx or 0,
                status_4xx=row.status_4xx or 0,
                status_5xx=row.status_5xx or 0,
                unique_ips=row.unique_ips or 0,
            )
            db.add(hourly)
        count += 1

    await db.commit()
    logger.info(f"Aggregated {count} hourly records")
    return count


async def aggregate_daily(db: AsyncSession, days_back: int = 2) -> int:
    """Aggregate traffic logs into daily buckets."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_back)

    result = await db.execute(
        select(
            TrafficLog.proxy_host_id,
            func.strftime('%Y-%m-%d', TrafficLog.timestamp).label('date'),
            func.count(TrafficLog.id).label('total_requests'),
            func.sum(TrafficLog.bytes_sent).label('bytes_sent'),
            func.sum(TrafficLog.bytes_received).label('bytes_received'),
            func.avg(TrafficLog.response_time).label('avg_response_time'),
            func.count(func.distinct(TrafficLog.client_ip)).label('unique_ips'),
        )
        .where(TrafficLog.timestamp >= start)
        .group_by(
            TrafficLog.proxy_host_id,
            func.strftime('%Y-%m-%d', TrafficLog.timestamp),
        )
    )
    rows = result.all()

    count = 0
    for row in rows:
        existing = await db.execute(
            select(AnalyticsDaily).where(
                and_(
                    AnalyticsDaily.proxy_host_id == row.proxy_host_id,
                    AnalyticsDaily.date == row.date,
                )
            )
        )
        daily = existing.scalar_one_or_none()

        # Count threats for this day/host
        threat_result = await db.execute(
            select(func.count(ThreatEvent.id)).where(
                and_(
                    func.strftime('%Y-%m-%d', ThreatEvent.timestamp) == row.date,
                    ThreatEvent.proxy_host_id == row.proxy_host_id if row.proxy_host_id else True,
                )
            )
        )
        threat_count = threat_result.scalar() or 0

        # Get top IPs
        top_ips_result = await db.execute(
            select(
                TrafficLog.client_ip,
                func.count(TrafficLog.id).label('cnt'),
            )
            .where(
                and_(
                    func.strftime('%Y-%m-%d', TrafficLog.timestamp) == row.date,
                    TrafficLog.proxy_host_id == row.proxy_host_id if row.proxy_host_id else True,
                )
            )
            .group_by(TrafficLog.client_ip)
            .order_by(func.count(TrafficLog.id).desc())
            .limit(10)
        )
        top_ips = [{"ip": r.client_ip, "count": r.cnt} for r in top_ips_result.all()]

        if daily:
            daily.total_requests = row.total_requests or 0
            daily.total_threats = threat_count
            daily.bytes_sent = row.bytes_sent or 0
            daily.bytes_received = row.bytes_received or 0
            daily.avg_response_time_ms = int(row.avg_response_time) if row.avg_response_time else None
            daily.unique_ips = row.unique_ips or 0
            daily.top_ips = json.dumps(top_ips)
        else:
            daily = AnalyticsDaily(
                id=str(uuid.uuid4()),
                proxy_host_id=row.proxy_host_id,
                date=row.date,
                total_requests=row.total_requests or 0,
                total_threats=threat_count,
                bytes_sent=row.bytes_sent or 0,
                bytes_received=row.bytes_received or 0,
                avg_response_time_ms=int(row.avg_response_time) if row.avg_response_time else None,
                unique_ips=row.unique_ips or 0,
                top_ips=json.dumps(top_ips),
            )
            db.add(daily)
        count += 1

    await db.commit()
    logger.info(f"Aggregated {count} daily records")
    return count


async def aggregate_geo(db: AsyncSession, days_back: int = 2) -> int:
    """Aggregate geographic traffic stats."""
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days_back)

    result = await db.execute(
        select(
            TrafficLog.proxy_host_id,
            func.strftime('%Y-%m-%d', TrafficLog.timestamp).label('date'),
            TrafficLog.country_code,
            func.count(TrafficLog.id).label('requests'),
            func.sum(TrafficLog.bytes_sent).label('bytes'),
        )
        .where(
            and_(
                TrafficLog.timestamp >= start,
                TrafficLog.country_code.isnot(None),
                TrafficLog.country_code != '',
            )
        )
        .group_by(
            TrafficLog.proxy_host_id,
            func.strftime('%Y-%m-%d', TrafficLog.timestamp),
            TrafficLog.country_code,
        )
    )
    rows = result.all()

    count = 0
    for row in rows:
        existing = await db.execute(
            select(AnalyticsGeo).where(
                and_(
                    AnalyticsGeo.proxy_host_id == row.proxy_host_id,
                    AnalyticsGeo.date == row.date,
                    AnalyticsGeo.country_code == row.country_code,
                )
            )
        )
        geo = existing.scalar_one_or_none()

        if geo:
            geo.requests = row.requests or 0
            geo.bytes = row.bytes or 0
        else:
            geo = AnalyticsGeo(
                id=str(uuid.uuid4()),
                proxy_host_id=row.proxy_host_id,
                date=row.date,
                country_code=row.country_code,
                requests=row.requests or 0,
                bytes=row.bytes or 0,
            )
            db.add(geo)
        count += 1

    await db.commit()
    logger.info(f"Aggregated {count} geo records")
    return count
