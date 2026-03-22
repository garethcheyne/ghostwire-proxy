from sqlalchemy import Column, String, DateTime, Float, BigInteger, Integer, Index
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class SystemMetrics(Base):
    """Stores periodic system metrics for historical monitoring."""
    __tablename__ = "system_metrics"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # CPU metrics
    cpu_usage = Column(Float, nullable=True)  # Percentage (0-100)
    cpu_count = Column(Integer, nullable=True)

    # Memory metrics
    memory_used = Column(BigInteger, nullable=True)  # Bytes
    memory_total = Column(BigInteger, nullable=True)  # Bytes
    memory_percent = Column(Float, nullable=True)  # Percentage (0-100)

    # Disk metrics
    disk_used = Column(BigInteger, nullable=True)  # Bytes
    disk_total = Column(BigInteger, nullable=True)  # Bytes
    disk_percent = Column(Float, nullable=True)  # Percentage (0-100)

    # Network metrics (since last measurement)
    network_bytes_sent = Column(BigInteger, nullable=True)
    network_bytes_recv = Column(BigInteger, nullable=True)

    # Request metrics (from traffic logs)
    request_count = Column(Integer, nullable=True)  # Requests in this interval
    active_connections = Column(Integer, nullable=True)

    # Database metrics
    db_connections = Column(Integer, nullable=True)
    db_size_bytes = Column(BigInteger, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_system_metrics_timestamp', 'timestamp'),
    )


class ContainerMetrics(Base):
    """Stores container-specific metrics."""
    __tablename__ = "container_metrics"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    container_name = Column(String(100), nullable=False)
    container_id = Column(String(64), nullable=True)
    status = Column(String(20), nullable=False)  # running, stopped, etc.

    # Resource usage
    cpu_percent = Column(Float, nullable=True)
    memory_used = Column(BigInteger, nullable=True)
    memory_limit = Column(BigInteger, nullable=True)
    memory_percent = Column(Float, nullable=True)

    # Network I/O
    network_rx_bytes = Column(BigInteger, nullable=True)
    network_tx_bytes = Column(BigInteger, nullable=True)

    # Uptime
    started_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('idx_container_metrics_timestamp', 'timestamp'),
        Index('idx_container_metrics_name_timestamp', 'container_name', 'timestamp'),
    )
