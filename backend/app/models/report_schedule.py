from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class ReportSchedule(Base):
    """A recurring emailed traffic report for one host (or the whole fleet).

    proxy_host_id NULL means "all hosts", matching the convention WAF rules,
    rate limits and GeoIP rules already use for global scope.
    """
    __tablename__ = "report_schedules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    proxy_host_id = Column(String(36), nullable=True, index=True)

    # daily | weekly | monthly
    frequency = Column(String(20), nullable=False, default="weekly")
    # Hour of day (UTC) to send. Reports summarise a period that has ended, so
    # sending early in the day gives a complete previous period.
    send_hour = Column(Integer, nullable=False, default=7)
    # 0=Monday..6=Sunday for weekly; day-of-month for monthly.
    send_day = Column(Integer, nullable=True)

    # Reporting window the email covers.
    period = Column(String(10), nullable=False, default="7d")

    # JSON array of email addresses.
    recipients = Column(Text, nullable=False, default="[]")

    enabled = Column(Boolean, default=True, nullable=False)

    last_sent_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(String(20), nullable=True)   # sent | failed
    last_error = Column(Text, nullable=True)
    send_count = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
