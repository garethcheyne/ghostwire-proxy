from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class ProxyHost(Base):
    __tablename__ = "proxy_hosts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Domain configuration
    domain_names = Column(JSON, nullable=False)  # List of domain names

    # Default upstream configuration (used for "/" location)
    forward_scheme = Column(String(10), default="http", nullable=False)  # http, https
    forward_host = Column(String(255), nullable=False)
    forward_port = Column(Integer, nullable=False)

    # SSL configuration
    ssl_enabled = Column(Boolean, default=False, nullable=False)
    ssl_force = Column(Boolean, default=False, nullable=False)
    certificate_id = Column(String(36), ForeignKey("certificates.id", ondelete="SET NULL"), nullable=True)

    # Features
    http2_support = Column(Boolean, default=True, nullable=False)
    hsts_enabled = Column(Boolean, default=False, nullable=False)
    hsts_subdomains = Column(Boolean, default=False, nullable=False)
    websockets_support = Column(Boolean, default=True, nullable=False)
    block_exploits = Column(Boolean, default=True, nullable=False)

    # Access control
    access_list_id = Column(String(36), ForeignKey("access_lists.id", ondelete="SET NULL"), nullable=True)
    auth_wall_id = Column(String(36), ForeignKey("auth_walls.id", ondelete="SET NULL"), nullable=True)

    # Location-level advanced config (inside default location block)
    advanced_config = Column(Text, nullable=True)

    # Server-level advanced config (outside location blocks, in server block)
    server_advanced_config = Column(Text, nullable=True)

    # Server-level settings
    client_max_body_size = Column(String(20), default="100m", nullable=False)
    proxy_buffering = Column(Boolean, default=True, nullable=False)
    proxy_buffer_size = Column(String(20), default="4k", nullable=False)
    proxy_buffers = Column(String(20), default="8 4k", nullable=False)

    # Caching configuration
    cache_enabled = Column(Boolean, default=False, nullable=False)
    cache_valid = Column(String(100), nullable=True)  # e.g., "200 302 10m"
    cache_bypass = Column(String(255), nullable=True)  # e.g., "$http_cache_control"

    # Rate limiting configuration
    rate_limit_enabled = Column(Boolean, default=False, nullable=False)
    rate_limit_requests = Column(Integer, default=100, nullable=False)  # requests per period
    rate_limit_period = Column(String(10), default="1s", nullable=False)  # 1s, 1m, etc.
    rate_limit_burst = Column(Integer, default=50, nullable=False)

    # Custom error pages
    custom_error_pages = Column(JSON, nullable=True)  # {"404": "/custom_404.html", "500": "/error.html"}

    # Traffic logging
    traffic_logging_enabled = Column(Boolean, default=False, nullable=False)

    # Status
    enabled = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    certificate = relationship("Certificate", back_populates="proxy_hosts")
    access_list = relationship("AccessList", back_populates="proxy_hosts")
    auth_wall = relationship("AuthWall", back_populates="proxy_hosts")
    upstream_servers = relationship("UpstreamServer", back_populates="proxy_host", cascade="all, delete-orphan")
    locations = relationship("ProxyLocation", back_populates="proxy_host", cascade="all, delete-orphan", order_by="desc(ProxyLocation.priority)")
    traffic_logs = relationship("TrafficLog", back_populates="proxy_host", cascade="all, delete-orphan")


class UpstreamServer(Base):
    __tablename__ = "upstream_servers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proxy_host_id = Column(String(36), ForeignKey("proxy_hosts.id", ondelete="CASCADE"), nullable=False, index=True)

    host = Column(String(255), nullable=False)
    port = Column(Integer, nullable=False)
    weight = Column(Integer, default=1, nullable=False)
    max_fails = Column(Integer, default=3, nullable=False)
    fail_timeout = Column(Integer, default=30, nullable=False)  # seconds

    enabled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    proxy_host = relationship("ProxyHost", back_populates="upstream_servers")


class ProxyLocation(Base):
    """Custom location blocks for a proxy host with different backends per path"""
    __tablename__ = "proxy_locations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proxy_host_id = Column(String(36), ForeignKey("proxy_hosts.id", ondelete="CASCADE"), nullable=False, index=True)

    # Location matching
    path = Column(String(255), nullable=False)  # e.g., "/api", "/static", "~ \.php$"
    match_type = Column(String(20), default="prefix", nullable=False)  # prefix, exact, regex, regex_case_insensitive
    priority = Column(Integer, default=0, nullable=False)  # Higher = processed first

    # Backend target
    forward_scheme = Column(String(10), default="http", nullable=False)
    forward_host = Column(String(255), nullable=False)
    forward_port = Column(Integer, nullable=False)

    # Location-specific settings
    websockets_support = Column(Boolean, default=False, nullable=False)

    # Caching
    cache_enabled = Column(Boolean, default=False, nullable=False)
    cache_valid = Column(String(100), nullable=True)  # e.g., "200 302 10m", "any 1h"
    cache_bypass = Column(String(255), nullable=True)  # e.g., "$http_cache_control"

    # Rate limiting
    rate_limit_enabled = Column(Boolean, default=False, nullable=False)
    rate_limit_requests = Column(Integer, default=100, nullable=False)  # requests per period
    rate_limit_period = Column(String(10), default="1s", nullable=False)  # 1s, 1m, etc.
    rate_limit_burst = Column(Integer, default=50, nullable=False)

    # Custom headers
    custom_headers = Column(JSON, nullable=True)  # {"X-Custom": "value", ...}
    proxy_headers = Column(JSON, nullable=True)  # Override proxy_set_header
    hide_headers = Column(JSON, nullable=True)  # Headers to remove from upstream response

    # Timeouts
    proxy_connect_timeout = Column(Integer, default=60, nullable=False)
    proxy_send_timeout = Column(Integer, default=60, nullable=False)
    proxy_read_timeout = Column(Integer, default=60, nullable=False)

    # Custom nginx directives for this location
    advanced_config = Column(Text, nullable=True)

    enabled = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    proxy_host = relationship("ProxyHost", back_populates="locations")
