from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class TrafficLog(Base):
    __tablename__ = "traffic_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    proxy_host_id = Column(String(36), ForeignKey("proxy_hosts.id", ondelete="CASCADE"), nullable=False, index=True)

    # Request info
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
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
    upstream_addr = Column(String(255), nullable=True)
    upstream_response_time = Column(Integer, nullable=True)  # milliseconds

    # SSL
    ssl_protocol = Column(String(20), nullable=True)
    ssl_cipher = Column(String(100), nullable=True)

    # User agent
    user_agent = Column(Text, nullable=True)
    referer = Column(Text, nullable=True)

    # Geo info (if available)
    country_code = Column(String(2), nullable=True)

    # Auth
    auth_user = Column(String(255), nullable=True)  # User from auth wall

    # Relationships
    proxy_host = relationship("ProxyHost", back_populates="traffic_logs")

    __table_args__ = (
        Index('idx_traffic_logs_host_timestamp', 'proxy_host_id', 'timestamp'),
        Index('idx_traffic_logs_timestamp_status', 'timestamp', 'status'),
    )
