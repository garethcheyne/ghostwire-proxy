from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class FirewallConnectorCreate(BaseModel):
    name: str
    connector_type: str
    host: str
    port: int | None = None
    username: str | None = None
    password: str | None = None
    api_key: str | None = None
    site_id: str | None = None
    address_list_name: str | None = None
    enabled: bool = True

    @field_validator('connector_type')
    @classmethod
    def validate_connector_type(cls, v: str) -> str:
        valid = ('routeros', 'unifi', 'pfsense', 'opnsense')
        if v not in valid:
            raise ValueError(f'Connector type must be one of: {", ".join(valid)}')
        return v


class FirewallConnectorUpdate(BaseModel):
    name: str | None = None
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None
    api_key: str | None = None
    site_id: str | None = None
    address_list_name: str | None = None
    enabled: bool | None = None


class FirewallConnectorResponse(BaseModel):
    id: str
    name: str
    connector_type: str
    host: str
    port: int | None
    username: str | None
    site_id: str | None
    address_list_name: str | None
    enabled: bool
    last_sync_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FirewallBlocklistResponse(BaseModel):
    id: str
    threat_actor_id: str | None
    ip_address: str
    connector_id: str | None
    pushed_at: datetime | None
    expires_at: datetime | None
    status: str
    error_message: str | None

    model_config = ConfigDict(from_attributes=True)
