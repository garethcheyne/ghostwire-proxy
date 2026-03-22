from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional


class FirewallConnectorCreate(BaseModel):
    name: str
    connector_type: str
    host: str
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    site_id: Optional[str] = None
    address_list_name: Optional[str] = None
    enabled: bool = True

    @field_validator('connector_type')
    @classmethod
    def validate_connector_type(cls, v: str) -> str:
        valid = ('routeros', 'unifi', 'pfsense', 'opnsense')
        if v not in valid:
            raise ValueError(f'Connector type must be one of: {", ".join(valid)}')
        return v


class FirewallConnectorUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    site_id: Optional[str] = None
    address_list_name: Optional[str] = None
    enabled: Optional[bool] = None


class FirewallConnectorResponse(BaseModel):
    id: str
    name: str
    connector_type: str
    host: str
    port: Optional[int]
    username: Optional[str]
    site_id: Optional[str]
    address_list_name: Optional[str]
    enabled: bool
    last_sync_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FirewallBlocklistResponse(BaseModel):
    id: str
    threat_actor_id: Optional[str]
    ip_address: str
    connector_id: Optional[str]
    pushed_at: Optional[datetime]
    expires_at: Optional[datetime]
    status: str
    error_message: Optional[str]

    class Config:
        from_attributes = True
