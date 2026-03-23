"""Update tracking models for self-update system."""

from sqlalchemy import Column, String, DateTime, Text, Boolean, Integer, JSON
from datetime import datetime, timezone
import uuid

from app.core.database import Base


class UpdateHistory(Base):
    """History of all update operations."""
    __tablename__ = "update_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    update_type = Column(String(20), nullable=False)  # 'app' or 'base_image'

    # Version info
    from_version = Column(String(100), nullable=True)
    to_version = Column(String(100), nullable=True)
    container_name = Column(String(100), nullable=True)  # For base image updates

    # Status
    status = Column(String(20), nullable=False, default='pending')
    # pending, in_progress, completed, failed, rolled_back
    error_message = Column(Text, nullable=True)

    # Rollback info
    backup_id = Column(String(36), nullable=True)  # Links to backups table
    can_rollback = Column(Boolean, default=True)
    rollback_performed = Column(Boolean, default=False)

    # Metadata
    initiated_by = Column(String(36), nullable=True)
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Detailed progress
    progress_percent = Column(Integer, default=0)
    progress_message = Column(String(500), nullable=True)
    steps_completed = Column(JSON, nullable=True)  # List of completed step names


class BaseImageVersion(Base):
    """Tracks base image versions for each container."""
    __tablename__ = "base_image_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    container_name = Column(String(100), nullable=False, unique=True)
    # api, ui, nginx, postgres, redis
    image_name = Column(String(200), nullable=False)
    # python:3.12-slim, node:20-alpine, etc.

    current_digest = Column(String(100), nullable=True)
    latest_digest = Column(String(100), nullable=True)
    current_tag = Column(String(50), nullable=True)
    latest_tag = Column(String(50), nullable=True)

    last_checked = Column(DateTime(timezone=True), nullable=True)
    update_available = Column(Boolean, default=False)
    security_update = Column(Boolean, default=False)  # If it's a security patch

    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class UpdateSettings(Base):
    """Update preferences and configuration."""
    __tablename__ = "update_settings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Auto-check settings
    auto_check_enabled = Column(Boolean, default=True)
    check_interval_hours = Column(Integer, default=24)
    last_check = Column(DateTime(timezone=True), nullable=True)

    # Notification settings
    notify_app_updates = Column(Boolean, default=True)
    notify_security_updates = Column(Boolean, default=True)
    notify_base_image_updates = Column(Boolean, default=False)

    # Auto-update settings (dangerous - disabled by default)
    auto_update_security = Column(Boolean, default=False)

    # Update source
    update_channel = Column(String(20), default="stable")  # stable, beta, edge

    # GitHub repository (for custom forks)
    github_repo = Column(String(200), default="garethcheyne/ghostwire-proxy")

    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
