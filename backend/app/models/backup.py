"""Backup model for storing backup metadata."""

from sqlalchemy import Column, String, DateTime, BigInteger, Boolean, Text
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class Backup(Base):
    """Stores metadata about backups."""
    __tablename__ = "backups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=False, default=0)

    # Backup type
    backup_type = Column(String(20), nullable=False)  # 'manual' or 'scheduled'

    # What's included
    includes_database = Column(Boolean, default=True)
    includes_certificates = Column(Boolean, default=True)
    includes_letsencrypt = Column(Boolean, default=True)
    includes_configs = Column(Boolean, default=True)
    includes_traffic_logs = Column(Boolean, default=False)

    # Status
    status = Column(String(20), nullable=False, default='pending')  # pending, in_progress, completed, failed
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Creator info
    created_by = Column(String(36), nullable=True)  # User ID


class BackupSettings(Base):
    """Stores backup configuration settings."""
    __tablename__ = "backup_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Schedule settings
    auto_backup_enabled = Column(Boolean, default=False)
    schedule_cron = Column(String(50), default="0 2 * * *")  # Default: 2 AM daily

    # Retention settings
    retention_days = Column(BigInteger, default=30)
    retention_count = Column(BigInteger, default=10)  # Keep at least N backups

    # Content settings
    include_traffic_logs = Column(Boolean, default=False)  # Large, optional

    # Encryption (for future use)
    encryption_enabled = Column(Boolean, default=False)

    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
