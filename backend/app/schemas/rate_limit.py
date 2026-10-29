from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class RateLimitRuleCreate(BaseModel):
    proxy_host_id: str | None = None
    name: str
    requests_per_second: int | None = None
    requests_per_minute: int | None = None
    requests_per_hour: int | None = None
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
    name: str | None = None
    requests_per_second: int | None = None
    requests_per_minute: int | None = None
    requests_per_hour: int | None = None
    burst_size: int | None = None
    action: str | None = None
    enabled: bool | None = None


class RateLimitRuleResponse(BaseModel):
    id: str
    proxy_host_id: str | None
    name: str
    requests_per_second: int | None
    requests_per_minute: int | None
    requests_per_hour: int | None
    burst_size: int
    action: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GeoipSettingsUpdate(BaseModel):
    provider: str | None = None
    database_path: str | None = None
    license_key: str | None = None
    auto_update: bool | None = None
    enabled: bool | None = None

    @field_validator('provider')
    @classmethod
    def validate_provider(cls, v: str | None) -> str | None:
        if v is not None:
            valid = ('maxmind', 'ip2location')
            if v not in valid:
                raise ValueError(f'Provider must be one of: {", ".join(valid)}')
        return v


class GeoipSettingsResponse(BaseModel):
    id: str
    provider: str
    database_path: str | None
    auto_update: bool
    last_updated_at: datetime | None
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class GeoipRuleCreate(BaseModel):
    proxy_host_id: str | None = None
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
    name: str | None = None
    mode: str | None = None
    countries: str | None = None
    action: str | None = None
    enabled: bool | None = None


class GeoipRuleResponse(BaseModel):
    id: str
    proxy_host_id: str | None
    name: str
    mode: str
    countries: str
    action: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GeoipLookupResponse(BaseModel):
    ip: str
    country_code: str | None
    country_name: str | None
    continent_code: str | None
