from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


class PushSubscriptionCreate(BaseModel):
    endpoint: str
    p256dh_key: str
    auth_key: str
    user_agent: Optional[str] = None


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
    config: Optional[str] = None  # JSON
    enabled: bool = True

    @field_validator('channel_type')
    @classmethod
    def validate_channel_type(cls, v: str) -> str:
        valid = ('push', 'email', 'webhook', 'slack', 'telegram')
        if v not in valid:
            raise ValueError(f'Channel type must be one of: {", ".join(valid)}')
        return v


class AlertChannelUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[str] = None
    enabled: Optional[bool] = None


class AlertChannelResponse(BaseModel):
    id: str
    user_id: Optional[str]
    channel_type: str
    name: str
    config: Optional[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AlertPreferenceCreate(BaseModel):
    alert_type: str
    min_severity: str = "medium"
    channels: Optional[str] = None  # JSON array of channel IDs
    enabled: bool = True

    @field_validator('alert_type')
    @classmethod
    def validate_alert_type(cls, v: str) -> str:
        valid = ('threat_detected', 'ip_blocked', 'firewall_pushed', 'cert_expiring', 'host_down')
        if v not in valid:
            raise ValueError(f'Alert type must be one of: {", ".join(valid)}')
        return v

    @field_validator('min_severity')
    @classmethod
    def validate_min_severity(cls, v: str) -> str:
        valid = ('low', 'medium', 'high', 'critical')
        if v not in valid:
            raise ValueError(f'Severity must be one of: {", ".join(valid)}')
        return v


class AlertPreferenceUpdate(BaseModel):
    min_severity: Optional[str] = None
    channels: Optional[str] = None
    enabled: Optional[bool] = None


class AlertPreferenceResponse(BaseModel):
    id: str
    user_id: str
    alert_type: str
    min_severity: str
    channels: Optional[str]
    enabled: bool

    class Config:
        from_attributes = True
