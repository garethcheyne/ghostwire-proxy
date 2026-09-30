from pydantic import BaseModel, field_validator, model_validator
from datetime import datetime
from typing import Optional
import ipaddress
import re


class ProxyHostRef(BaseModel):
    """A proxy host that uses an access list or auth wall."""
    id: str
    domain_names: list[str]

    class Config:
        from_attributes = True


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


BLOCKED_BEHAVIORS = ('403', 'congratulations', 'redirect', '404', '444')


def _check_blocked_behavior(v: Optional[str]) -> Optional[str]:
    if v is not None and v not in BLOCKED_BEHAVIORS:
        raise ValueError(f"Blocked behaviour must be one of: {', '.join(BLOCKED_BEHAVIORS)}")
    return v


def _check_redirect_url(v: Optional[str]) -> Optional[str]:
    """The URL is written into the nginx config, so accept only a plain http(s) URL."""
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    if not re.fullmatch(r"https?://[^\s\"';{}]+", v):
        raise ValueError('Redirect URL must be a full http:// or https:// URL without spaces, quotes, ; or braces')
    return v


class AccessListBase(BaseModel):
    name: str
    mode: str = "blacklist"
    default_action: str = "allow"
    blocked_behavior: str = "403"
    blocked_redirect_url: Optional[str] = None

    @field_validator('blocked_behavior')
    @classmethod
    def blocked_behavior_valid(cls, v):
        return _check_blocked_behavior(v)

    @field_validator('blocked_redirect_url')
    @classmethod
    def blocked_redirect_url_valid(cls, v):
        return _check_redirect_url(v)

    @model_validator(mode='after')
    def redirect_needs_url(self):
        if self.blocked_behavior == 'redirect' and not self.blocked_redirect_url:
            raise ValueError('A redirect needs a Redirect URL')
        return self

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
    blocked_behavior: Optional[str] = None
    blocked_redirect_url: Optional[str] = None

    @field_validator('blocked_behavior')
    @classmethod
    def blocked_behavior_valid(cls, v):
        return _check_blocked_behavior(v)

    @field_validator('blocked_redirect_url')
    @classmethod
    def blocked_redirect_url_valid(cls, v):
        return _check_redirect_url(v)
    # When given, replaces every entry (in this order)
    entries: Optional[list[AccessListEntryCreate]] = None

    @field_validator('mode')
    @classmethod
    def mode_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ('whitelist', 'blacklist'):
            raise ValueError('Mode must be whitelist or blacklist')
        return v


class AccessListResponse(BaseModel):
    id: str
    name: str
    mode: str
    default_action: str
    blocked_behavior: str = "403"
    blocked_redirect_url: Optional[str] = None
    entries: list[AccessListEntryResponse] = []
    proxy_hosts: list[ProxyHostRef] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
