"""Pydantic schemas for backup operations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    created_by: str | None = None

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


class BackupSettingsUpdate(BaseModel):
    """Schema for updating backup settings."""

    auto_backup_enabled: bool | None = None
    schedule_cron: str | None = Field(None, pattern=r"^[\d\*\/\-\,]+(\s+[\d\*\/\-\,]+){4}$")
    retention_days: int | None = Field(None, ge=1, le=365)
    retention_count: int | None = Field(None, ge=1, le=100)
    include_traffic_logs: bool | None = None


class RestoreRequest(BaseModel):
    """Schema for restore request."""

    backup_id: str | None = None
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
