"""Pydantic schemas for backup operations."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class BackupCreate(BaseModel):
    """Schema for creating a new backup."""
    include_database: bool = True
    include_certificates: bool = True
    include_letsencrypt: bool = True
    include_configs: bool = True
    include_traffic_logs: bool = False


class BackupResponse(BaseModel):
    """Schema for backup response."""
    id: str
    filename: str
    file_size: int
    backup_type: str
    includes_database: bool
    includes_certificates: bool
    includes_letsencrypt: bool
    includes_configs: bool
    includes_traffic_logs: bool
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class BackupListResponse(BaseModel):
    """Schema for listing backups."""
    backups: list[BackupResponse]
    total: int


class BackupSettingsResponse(BaseModel):
    """Schema for backup settings response."""
    auto_backup_enabled: bool
    schedule_cron: str
    retention_days: int
    retention_count: int
    include_traffic_logs: bool
    encryption_enabled: bool

    class Config:
        from_attributes = True


class BackupSettingsUpdate(BaseModel):
    """Schema for updating backup settings."""
    auto_backup_enabled: Optional[bool] = None
    schedule_cron: Optional[str] = Field(None, pattern=r"^[\d\*\/\-\,]+(\s+[\d\*\/\-\,]+){4}$")
    retention_days: Optional[int] = Field(None, ge=1, le=365)
    retention_count: Optional[int] = Field(None, ge=1, le=100)
    include_traffic_logs: Optional[bool] = None


class RestoreRequest(BaseModel):
    """Schema for restore request."""
    backup_id: Optional[str] = None
    restore_database: bool = True
    restore_certificates: bool = True
    restore_letsencrypt: bool = True
    restore_configs: bool = True


class RestoreResponse(BaseModel):
    """Schema for restore operation response."""
    status: str
    message: str
    restored_items: list[str]
    warnings: list[str] = []
