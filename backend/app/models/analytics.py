from sqlalchemy import Column, String, DateTime, Integer, Index
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class AnalyticsHourly(Base):
    __tablename__ = "analytics_hourly"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proxy_host_id = Column(String(36), nullable=True)  # NULL = global
    hour = Column(String(20), nullable=False)  # '2024-01-15T14:00:00'
    total_requests = Column(Integer, default=0)
    blocked_requests = Column(Integer, default=0)
    bytes_sent = Column(Integer, default=0)
    bytes_received = Column(Integer, default=0)
    avg_response_time_ms = Column(Integer, nullable=True)
    status_2xx = Column(Integer, default=0)
    status_3xx = Column(Integer, default=0)
    status_4xx = Column(Integer, default=0)
    status_5xx = Column(Integer, default=0)
    unique_ips = Column(Integer, default=0)

    __table_args__ = (
        Index('idx_analytics_hourly_host_hour', 'proxy_host_id', 'hour', unique=True),
    )


class AnalyticsDaily(Base):
    __tablename__ = "analytics_daily"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proxy_host_id = Column(String(36), nullable=True)
    date = Column(String(10), nullable=False)  # '2024-01-15'
    total_requests = Column(Integer, default=0)
    blocked_requests = Column(Integer, default=0)
    total_threats = Column(Integer, default=0)
    bytes_sent = Column(Integer, default=0)
    bytes_received = Column(Integer, default=0)
    avg_response_time_ms = Column(Integer, nullable=True)
    unique_ips = Column(Integer, default=0)
    top_countries = Column(String, nullable=True)  # JSON
    top_ips = Column(String, nullable=True)  # JSON

    __table_args__ = (
        Index('idx_analytics_daily_host_date', 'proxy_host_id', 'date', unique=True),
    )


class AnalyticsGeo(Base):
    __tablename__ = "analytics_geo"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proxy_host_id = Column(String(36), nullable=True)
    date = Column(String(10), nullable=False)
    country_code = Column(String(5), nullable=False)
    requests = Column(Integer, default=0)
    blocked = Column(Integer, default=0)
    threats = Column(Integer, default=0)
    bytes = Column(Integer, default=0)

    __table_args__ = (
        Index('idx_analytics_geo_host_date_country', 'proxy_host_id', 'date', 'country_code', unique=True),
    )
