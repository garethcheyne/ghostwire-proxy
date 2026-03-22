from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


class RateLimitRuleCreate(BaseModel):
    proxy_host_id: Optional[str] = None
    name: str
    requests_per_second: Optional[int] = None
    requests_per_minute: Optional[int] = None
    requests_per_hour: Optional[int] = None
    burst_size: int = 10
    action: str = "reject"
    enabled: bool = True

    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        valid = ('reject', 'delay', 'log')
        if v not in valid:
            raise ValueError(f'Action must be one of: {", ".join(valid)}')
        return v


class RateLimitRuleUpdate(BaseModel):
    name: Optional[str] = None
    requests_per_second: Optional[int] = None
    requests_per_minute: Optional[int] = None
    requests_per_hour: Optional[int] = None
    burst_size: Optional[int] = None
    action: Optional[str] = None
    enabled: Optional[bool] = None


class RateLimitRuleResponse(BaseModel):
    id: str
    proxy_host_id: Optional[str]
    name: str
    requests_per_second: Optional[int]
    requests_per_minute: Optional[int]
    requests_per_hour: Optional[int]
    burst_size: int
    action: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GeoipSettingsUpdate(BaseModel):
    provider: Optional[str] = None
    database_path: Optional[str] = None
    license_key: Optional[str] = None
    auto_update: Optional[bool] = None
    enabled: Optional[bool] = None

    @field_validator('provider')
    @classmethod
    def validate_provider(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            valid = ('maxmind', 'ip2location')
            if v not in valid:
                raise ValueError(f'Provider must be one of: {", ".join(valid)}')
        return v


class GeoipSettingsResponse(BaseModel):
    id: str
    provider: str
    database_path: Optional[str]
    auto_update: bool
    last_updated_at: Optional[datetime]
    enabled: bool

    class Config:
        from_attributes = True


class GeoipRuleCreate(BaseModel):
    proxy_host_id: Optional[str] = None
    name: str
    mode: str = "blocklist"
    countries: str  # JSON array
    action: str = "block"
    enabled: bool = True

    @field_validator('mode')
    @classmethod
    def validate_mode(cls, v: str) -> str:
        valid = ('blocklist', 'allowlist')
        if v not in valid:
            raise ValueError(f'Mode must be one of: {", ".join(valid)}')
        return v

    @field_validator('action')
    @classmethod
    def validate_action(cls, v: str) -> str:
        valid = ('block', 'log', 'challenge')
        if v not in valid:
            raise ValueError(f'Action must be one of: {", ".join(valid)}')
        return v


class GeoipRuleUpdate(BaseModel):
    name: Optional[str] = None
    mode: Optional[str] = None
    countries: Optional[str] = None
    action: Optional[str] = None
    enabled: Optional[bool] = None


class GeoipRuleResponse(BaseModel):
    id: str
    proxy_host_id: Optional[str]
    name: str
    mode: str
    countries: str
    action: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GeoipLookupResponse(BaseModel):
    ip: str
    country_code: Optional[str]
    country_name: Optional[str]
    continent_code: Optional[str]
