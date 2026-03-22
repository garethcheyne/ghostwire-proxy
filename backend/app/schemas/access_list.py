from pydantic import BaseModel, field_validator
from datetime import datetime
from typing import Optional
import ipaddress


class AccessListEntryCreate(BaseModel):
    ip_or_cidr: str
    action: str = "deny"
    description: Optional[str] = None

    @field_validator('ip_or_cidr')
    @classmethod
    def validate_ip_or_cidr(cls, v: str) -> str:
        try:
            # Try as IP address
            ipaddress.ip_address(v)
        except ValueError:
            try:
                # Try as CIDR network
                ipaddress.ip_network(v, strict=False)
            except ValueError:
                raise ValueError('Invalid IP address or CIDR notation')
        return v

    @field_validator('action')
    @classmethod
    def action_valid(cls, v: str) -> str:
        if v not in ('allow', 'deny'):
            raise ValueError('Action must be allow or deny')
        return v


class AccessListEntryResponse(BaseModel):
    id: str
    access_list_id: str
    ip_or_cidr: str
    action: str
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AccessListBase(BaseModel):
    name: str
    mode: str = "blacklist"
    default_action: str = "allow"

    @field_validator('mode')
    @classmethod
    def mode_valid(cls, v: str) -> str:
        if v not in ('whitelist', 'blacklist'):
            raise ValueError('Mode must be whitelist or blacklist')
        return v

    @field_validator('default_action')
    @classmethod
    def default_action_valid(cls, v: str) -> str:
        if v not in ('allow', 'deny'):
            raise ValueError('Default action must be allow or deny')
        return v


class AccessListCreate(AccessListBase):
    entries: Optional[list[AccessListEntryCreate]] = None


class AccessListUpdate(BaseModel):
    name: Optional[str] = None
    mode: Optional[str] = None
    default_action: Optional[str] = None


class AccessListResponse(BaseModel):
    id: str
    name: str
    mode: str
    default_action: str
    entries: list[AccessListEntryResponse] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
