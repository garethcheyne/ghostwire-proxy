from sqlalchemy import Column, String, Boolean, DateTime, Text
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class DnsProvider(Base):
    """DNS Provider configuration (Cloudflare, GoDaddy, etc.)"""
    __tablename__ = "dns_providers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)

    # Provider type: 'cloudflare', 'godaddy', 'route53', etc.
    provider_type = Column(String(50), nullable=False)

    # API credentials (encrypted)
    api_key = Column(Text, nullable=True)  # Encrypted - Cloudflare API token
    api_secret = Column(Text, nullable=True)  # Encrypted - for providers that need it
    account_id = Column(String(255), nullable=True)  # Cloudflare account ID

    # For Cloudflare: email if using global API key
    email = Column(String(255), nullable=True)

    # Status
    enabled = Column(Boolean, default=True, nullable=False)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class DnsZone(Base):
    """DNS Zone (domain) from a provider"""
    __tablename__ = "dns_zones"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_id = Column(String(36), nullable=False, index=True)

    # Zone info from provider
    zone_id = Column(String(255), nullable=False)  # Provider's zone ID
    name = Column(String(255), nullable=False)  # Domain name (e.g., example.com)

    # Status from provider
    status = Column(String(50), nullable=True)  # active, pending, etc.

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
