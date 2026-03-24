"""Honeypot trap models for catching and profiling scanners/attackers."""

from sqlalchemy import Column, String, DateTime, Text, Integer, Boolean, Index, ForeignKey, UniqueConstraint
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class HoneypotTrap(Base):
    """Configurable fake endpoints that catch scanners."""
    __tablename__ = "honeypot_traps"
    __table_args__ = (
        UniqueConstraint('path', 'proxy_host_id', name='uq_trap_path_host'),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    path = Column(String(500), nullable=False)  # e.g. /wp-login.php
    proxy_host_id = Column(String(36), ForeignKey("proxy_hosts.id", ondelete="CASCADE"), nullable=True)  # NULL = all hosts
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    trap_type = Column(String(30), default="generic")  # wordpress, phpmyadmin, admin, api, generic
    response_code = Column(Integer, default=200)  # HTTP status to return
    response_body = Column(Text, nullable=True)  # Fake page content
    severity = Column(String(20), default="high")  # Severity when triggered
    auto_block = Column(Boolean, default=True)  # Auto-block the IP
    enabled = Column(Boolean, default=True, nullable=False)
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class HoneypotHit(Base):
    """Record of a scanner/attacker hitting a honeypot trap."""
    __tablename__ = "honeypot_hits"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trap_id = Column(String(36), nullable=False, index=True)
    trap_path = Column(String(500), nullable=False)
    client_ip = Column(String(45), nullable=False, index=True)

    # Request details
    request_method = Column(String(10), nullable=True)
    request_uri = Column(Text, nullable=True)
    request_headers = Column(Text, nullable=True)  # JSON
    request_body = Column(Text, nullable=True)  # Captured POST body (truncated)
    user_agent = Column(Text, nullable=True)
    host = Column(String(255), nullable=True)
    referer = Column(Text, nullable=True)

    # GeoIP info (from Lua)
    country_code = Column(String(5), nullable=True)
    country_name = Column(String(100), nullable=True)

    # Action taken
    action_taken = Column(String(20), default="logged")  # logged, blocked, enriched

    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index('idx_honeypot_hits_ip_timestamp', 'client_ip', 'timestamp'),
    )


class IpEnrichment(Base):
    """Enriched intelligence data about an IP address."""
    __tablename__ = "ip_enrichments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ip_address = Column(String(45), unique=True, nullable=False, index=True)

    # GeoIP
    country_code = Column(String(5), nullable=True)
    country_name = Column(String(100), nullable=True)
    city = Column(String(255), nullable=True)
    region = Column(String(255), nullable=True)
    latitude = Column(String(20), nullable=True)
    longitude = Column(String(20), nullable=True)
    timezone = Column(String(100), nullable=True)

    # Network info
    isp = Column(String(255), nullable=True)
    org = Column(String(255), nullable=True)
    asn = Column(String(20), nullable=True)
    as_name = Column(String(255), nullable=True)
    reverse_dns = Column(String(255), nullable=True)

    # Abuse / reputation
    abuse_score = Column(Integer, nullable=True)  # AbuseIPDB confidence score 0-100
    abuse_reports = Column(Integer, nullable=True)
    abuse_last_reported = Column(DateTime(timezone=True), nullable=True)
    is_tor = Column(Boolean, nullable=True)
    is_proxy = Column(Boolean, nullable=True)
    is_vpn = Column(Boolean, nullable=True)
    is_datacenter = Column(Boolean, nullable=True)
    is_crawler = Column(Boolean, nullable=True)

    # Raw data
    raw_data = Column(Text, nullable=True)  # JSON dump of all enrichment sources

    # Meta
    enriched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
