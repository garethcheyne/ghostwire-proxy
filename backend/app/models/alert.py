from sqlalchemy import Column, String, DateTime, Text, Boolean, Index
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    endpoint = Column(Text, nullable=False)
    p256dh_key = Column(Text, nullable=False)
    auth_key = Column(Text, nullable=False)
    user_agent = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AlertChannel(Base):
    __tablename__ = "alert_channels"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=True, index=True)  # NULL = global
    channel_type = Column(String(20), nullable=False)  # push, email, webhook, slack, telegram
    name = Column(String(255), nullable=False)
    config = Column(Text, nullable=True)  # JSON config
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AlertPreference(Base):
    __tablename__ = "alert_preferences"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    alert_type = Column(String(50), nullable=False)  # threat_detected, ip_blocked, firewall_pushed, cert_expiring
    min_severity = Column(String(20), default="medium")
    channels = Column(Text, nullable=True)  # JSON array of channel IDs
    enabled = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        Index('idx_alert_preferences_user_type', 'user_id', 'alert_type'),
    )
