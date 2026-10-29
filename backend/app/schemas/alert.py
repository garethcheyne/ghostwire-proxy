from datetime import datetime

from pydantic import BaseModel, field_validator


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    p256dh_key: str
    auth_key: str
    user_agent: str | None = None


class PushSubscriptionResponse(BaseModel):
    id: str
    user_id: str
    endpoint: str
    created_at: datetime

    class Config:
        from_attributes = True


class AlertChannelCreate(BaseModel):
    channel_type: str
    name: str
    config: str | None = None  # JSON
    enabled: bool = True

    @field_validator('channel_type')
    @classmethod
    def validate_channel_type(cls, v: str) -> str:
        valid = ('push', 'email', 'webhook', 'slack', 'telegram')
        if v not in valid:
            raise ValueError(f'Channel type must be one of: {", ".join(valid)}')
        return v


class AlertChannelUpdate(BaseModel):
    name: str | None = None
    config: str | None = None
    enabled: bool | None = None


class AlertChannelResponse(BaseModel):
    id: str
    user_id: str | None
    channel_type: str
    name: str
    config: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Every alert type a preference can be set for. The per-backend-server types
# follow the user's host_down preference until they have one of their own
# (see alert_service.PREFERENCE_FALLBACK).
ALERT_TYPES = (
    'threat_detected',
    'ip_blocked',
    'firewall_pushed',
    'cert_expiring',
    'host_down',
    'upstream_server_down',
    'upstream_server_recovered',
)


class AlertPreferenceCreate(BaseModel):
    alert_type: str
    min_severity: str = "medium"
    channels: str | None = None  # JSON array of channel IDs
    enabled: bool = True

    @field_validator('alert_type')
    @classmethod
    def validate_alert_type(cls, v: str) -> str:
        if v not in ALERT_TYPES:
            raise ValueError(f'Alert type must be one of: {", ".join(ALERT_TYPES)}')
        return v

    @field_validator('min_severity')
    @classmethod
    def validate_min_severity(cls, v: str) -> str:
        valid = ('low', 'medium', 'high', 'critical')
        if v not in valid:
            raise ValueError(f'Severity must be one of: {", ".join(valid)}')
        return v


class AlertPreferenceUpdate(BaseModel):
    min_severity: str | None = None
    channels: str | None = None
    enabled: bool | None = None


class AlertPreferenceResponse(BaseModel):
    id: str
    user_id: str
    alert_type: str
    min_severity: str
    channels: str | None
    enabled: bool

    class Config:
        from_attributes = True
