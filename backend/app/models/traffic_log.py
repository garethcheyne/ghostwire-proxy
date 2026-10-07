from sqlalchemy import Column, String, DateTime, Integer, SmallInteger, Text, Boolean, ForeignKey, Index, JSON, text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.core.database import Base


# The upstream that produced the response: nginx records "a:1, b:2" when it
# retried, and the last one answered. Host part without the port, for grouping
# one VM's ports together. Immutable expressions, so they can be indexed.
UPSTREAM_SQL = r"regexp_replace(coalesce(upstream_addr, ''), '^.*,\s*', '')"
UPSTREAM_HOST_SQL = r"regexp_replace(regexp_replace(coalesce(upstream_addr, ''), '^.*,\s*', ''), ':[0-9]+$', '')"


class TrafficLog(Base):
    __tablename__ = "traffic_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Not indexed alone: idx_traffic_logs_host_timestamp leads with it.
    proxy_host_id = Column(String(36), ForeignKey("proxy_hosts.id", ondelete="CASCADE"), nullable=False)

    # Request info
    # Not indexed alone: idx_traffic_logs_timestamp_status leads with it.
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    client_ip = Column(String(45), nullable=False, index=True)  # IPv6 can be up to 45 chars

    # HTTP request
    request_method = Column(String(10), nullable=False)
    request_uri = Column(Text, nullable=False)
    query_string = Column(Text, nullable=True)
    request_headers = Column(Text, nullable=True)  # JSON

    # HTTP response
    status = Column(Integer, nullable=False, index=True)
    response_time = Column(Integer, nullable=True)  # milliseconds
    bytes_sent = Column(Integer, nullable=True)
    bytes_received = Column(Integer, nullable=True)

    # Upstream
    # Every address nginx tried, as it reports them ("a:1, b:2"); the last answered.
    upstream_addr = Column(String(255), nullable=True)
    upstream_response_time = Column(Integer, nullable=True)  # milliseconds, final attempt
    # Load balancing (migration 0016). The final attempt's status, how many
    # servers were tried, whether nginx failed over, each attempt as
    # [{"addr", "status", "ms"}], and the UpstreamServer row that answered
    # (soft reference: no FK, so deleting a server never touches the logs).
    upstream_status = Column(Integer, nullable=True)
    upstream_attempts = Column(SmallInteger, nullable=True)
    upstream_failover = Column(Boolean, nullable=True)
    upstream_attempt_log = Column(JSON, nullable=True)
    upstream_server_id = Column(String(36), nullable=True)

    # SSL
    ssl_protocol = Column(String(20), nullable=True)
    ssl_cipher = Column(String(100), nullable=True)

    # User agent
    user_agent = Column(Text, nullable=True)
    referer = Column(Text, nullable=True)

    # Geo info (if available)
    country_code = Column(String(2), nullable=True)
    country_name = Column(String(100), nullable=True)

    # Auth
    auth_user = Column(String(255), nullable=True)

    # Client classification. NULL means "not classified" (rows written before
    # this existed), which is deliberately distinct from False.
    is_bot = Column(Boolean, nullable=True, index=True)
    # Long-lived connections (websocket upgrades, SSE streams). Their duration
    # measures how long someone stayed connected, not how slow the server was,
    # so they are excluded from latency statistics.
    is_streaming = Column(Boolean, nullable=True)  # User from auth wall

    # Relationships
    proxy_host = relationship("ProxyHost", back_populates="traffic_logs")

    __table_args__ = (
        Index('idx_traffic_logs_host_timestamp', 'proxy_host_id', 'timestamp'),
        Index('idx_traffic_logs_timestamp_status', 'timestamp', 'status'),
        # Backend (VM) drill-down: the upstream's host part, port dropped, from the
        # last address nginx tried. Queries must use UPSTREAM_HOST_SQL verbatim
        # or the planner won't use it.
        Index('idx_traffic_logs_upstream_host_ts', text(UPSTREAM_HOST_SQL), 'timestamp'),
        # Per-backend breakdown of a load-balanced host (migration 0016)
        Index('idx_traffic_logs_host_upstream_server_ts', 'proxy_host_id', 'upstream_server_id', 'timestamp'),
    )
