from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, Index
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class FirewallConnector(Base):
    __tablename__ = "firewall_connectors"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    connector_type = Column(String(20), nullable=False)  # routeros, unifi, pfsense, opnsense
    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=True)
    username = Column(String(255), nullable=True)
    password = Column(Text, nullable=True)  # Encrypted
    api_key = Column(Text, nullable=True)  # Encrypted (for UniFi)
    site_id = Column(String(100), nullable=True)  # UniFi site
    address_list_name = Column(String(100), nullable=True)  # RouterOS address list name
    enabled = Column(Boolean, default=True, nullable=False)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class FirewallBlocklist(Base):
    __tablename__ = "firewall_blocklist"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    threat_actor_id = Column(String(36), nullable=True, index=True)
    ip_address = Column(String(45), nullable=False, index=True)
    connector_id = Column(String(36), nullable=True, index=True)
    pushed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # NULL = permanent
    status = Column(String(20), default="pending")  # pending, pushed, expired, removed
    error_message = Column(Text, nullable=True)

    __table_args__ = (
        Index('idx_firewall_blocklist_status', 'status'),
    )
