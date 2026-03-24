from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, Index, ForeignKey
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class RateLimitRule(Base):
    __tablename__ = "rate_limit_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proxy_host_id = Column(String(36), ForeignKey("proxy_hosts.id", ondelete="CASCADE"), nullable=True, index=True)  # NULL = global
    name = Column(String(255), nullable=False)
    requests_per_second = Column(Integer, nullable=True)
    requests_per_minute = Column(Integer, nullable=True)
    requests_per_hour = Column(Integer, nullable=True)
    burst_size = Column(Integer, default=10)
    action = Column(String(20), default="reject")  # reject, delay, log
    enabled = Column(Boolean, default=True, nullable=False)
    preset_id = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class GeoipSettings(Base):
    __tablename__ = "geoip_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(String(20), nullable=False)  # maxmind, ip2location
    database_path = Column(Text, nullable=True)
    license_key = Column(Text, nullable=True)  # Encrypted
    auto_update = Column(Boolean, default=True, nullable=False)
    last_updated_at = Column(DateTime(timezone=True), nullable=True)
    enabled = Column(Boolean, default=True, nullable=False)


class GeoipRule(Base):
    __tablename__ = "geoip_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proxy_host_id = Column(String(36), ForeignKey("proxy_hosts.id", ondelete="CASCADE"), nullable=True, index=True)  # NULL = global
    name = Column(String(255), nullable=False)
    mode = Column(String(20), default="blocklist")  # blocklist, allowlist
    countries = Column(Text, nullable=False)  # JSON array of country codes
    action = Column(String(20), default="block")  # block, log, challenge
    enabled = Column(Boolean, default=True, nullable=False)
    preset_id = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
