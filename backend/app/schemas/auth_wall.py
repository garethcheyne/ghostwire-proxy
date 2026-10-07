import re

from pydantic import BaseModel, EmailStr, Field, computed_field, field_validator
from datetime import datetime
from typing import Optional

from app.schemas.access_list import ProxyHostRef
from app.services.auth_wall_access import clean_list, normalize_domain, normalize_email, open_to_any_account


# Local Auth Users (Basic Auth)
class LocalAuthUserCreate(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    email: Optional[EmailStr] = None


class LocalAuthUserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None


class LocalAuthUserResponse(BaseModel):
    id: str
    auth_wall_id: str
    username: str
    display_name: Optional[str]
    email: Optional[str]
    is_active: bool
    totp_enabled: bool = False
    totp_verified: bool = False
    failed_attempts: int = 0
    locked_until: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# TOTP Setup schemas
class TotpSetupResponse(BaseModel):
    """Response when initiating TOTP setup - contains secret and QR code."""
    secret: str
    provisioning_uri: str
    backup_codes: list[str]


class TotpVerifyRequest(BaseModel):
    """Request to verify TOTP code during setup or login."""
    code: str


class TotpVerifyResponse(BaseModel):
    """Response after TOTP verification."""
    valid: bool
    message: str = ""


# OAuth Providers
class AuthProviderCreate(BaseModel):
    name: str
    provider_type: str  # google, github, azure_ad, oidc
    client_id: str
    client_secret: str
    authorization_url: Optional[str] = None
    token_url: Optional[str] = None
    userinfo_url: Optional[str] = None
    scopes: str = "openid email profile"
    enabled: bool = True

    @field_validator('provider_type')
    @classmethod
    def provider_type_valid(cls, v: str) -> str:
        valid_types = ('google', 'github', 'azure_ad', 'oidc')
        if v not in valid_types:
            raise ValueError(f'Provider type must be one of: {", ".join(valid_types)}')
        return v


class AuthProviderUpdate(BaseModel):
    name: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    authorization_url: Optional[str] = None
    token_url: Optional[str] = None
    userinfo_url: Optional[str] = None
    scopes: Optional[str] = None
    enabled: Optional[bool] = None


class AuthProviderResponse(BaseModel):
    id: str
    auth_wall_id: str
    name: str
    provider_type: str
    client_id: Optional[str]
    authorization_url: Optional[str]
    token_url: Optional[str]
    userinfo_url: Optional[str]
    scopes: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# LDAP Config
class LdapConfigCreate(BaseModel):
    name: str
    host: str
    port: int = 389
    use_ssl: bool = False
    use_starttls: bool = False
    bind_dn: Optional[str] = None
    bind_password: Optional[str] = None
    base_dn: str
    user_filter: str = "(uid=%s)"
    username_attribute: str = "uid"
    email_attribute: Optional[str] = "mail"
    display_name_attribute: Optional[str] = "cn"
    enabled: bool = True


class LdapConfigUpdate(BaseModel):
    name: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    use_ssl: Optional[bool] = None
    use_starttls: Optional[bool] = None
    bind_dn: Optional[str] = None
    bind_password: Optional[str] = None
    base_dn: Optional[str] = None
    user_filter: Optional[str] = None
    username_attribute: Optional[str] = None
    email_attribute: Optional[str] = None
    display_name_attribute: Optional[str] = None
    enabled: Optional[bool] = None


class LdapConfigResponse(BaseModel):
    id: str
    auth_wall_id: str
    name: str
    host: str
    port: int
    use_ssl: bool
    use_starttls: bool
    bind_dn: Optional[str]
    base_dn: str
    user_filter: str
    username_attribute: str
    email_attribute: Optional[str]
    display_name_attribute: Optional[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Auth Wall
# The name and theme are written into nginx config (a quoted `set` value and an
# alias path), so they are limited to characters that cannot break out of it.
_WALL_NAME_FORBIDDEN = re.compile(r'["\\;{}$`\r\n]')
_THEME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,49}$")


def _check_wall_name(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    v = v.strip()
    if not v:
        raise ValueError("Name is required")
    if _WALL_NAME_FORBIDDEN.search(v):
        raise ValueError('Name cannot contain quotes, backslashes, ;, {, }, $ or line breaks')
    return v


def _check_theme(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    if not _THEME_RE.match(v):
        raise ValueError("Theme must be a portal theme directory name (a-z, 0-9, - and _)")
    return v


class AuthWallAllowList(BaseModel):
    """Who may pass through an OAuth provider. Both empty = any account."""
    allowed_emails: Optional[list[str]] = None
    allowed_email_domains: Optional[list[str]] = None

    @field_validator('allowed_emails')
    @classmethod
    def emails_valid(cls, v):
        return None if v is None else clean_list(v, normalize_email)

    @field_validator('allowed_email_domains')
    @classmethod
    def domains_valid(cls, v):
        return None if v is None else clean_list(v, normalize_domain)


class AuthWallBase(AuthWallAllowList):
    name: str
    auth_type: str = "basic"
    session_timeout: int = 3600
    theme: str = "default"  # Auth portal theme directory
    default_provider_id: Optional[str] = None

    @field_validator('auth_type')
    @classmethod
    def auth_type_valid(cls, v: str) -> str:
        valid_types = ('basic', 'oauth', 'ldap', 'multi')
        if v not in valid_types:
            raise ValueError(f'Auth type must be one of: {", ".join(valid_types)}')
        return v

    @field_validator('name')
    @classmethod
    def name_valid(cls, v):
        return _check_wall_name(v)

    @field_validator('theme')
    @classmethod
    def theme_valid(cls, v):
        return _check_theme(v)


class AuthWallCreate(AuthWallBase):
    local_users: Optional[list[LocalAuthUserCreate]] = None
    auth_providers: Optional[list[AuthProviderCreate]] = None
    ldap_configs: Optional[list[LdapConfigCreate]] = None


class AuthWallUpdate(AuthWallAllowList):
    name: Optional[str] = None
    auth_type: Optional[str] = None
    session_timeout: Optional[int] = None
    theme: Optional[str] = None
    default_provider_id: Optional[str] = None

    @field_validator('auth_type')
    @classmethod
    def auth_type_valid(cls, v):
        if v is not None and v not in ('basic', 'oauth', 'ldap', 'multi'):
            raise ValueError('Auth type must be one of: basic, oauth, ldap, multi')
        return v

    @field_validator('name')
    @classmethod
    def name_valid(cls, v):
        return _check_wall_name(v)

    @field_validator('theme')
    @classmethod
    def theme_valid(cls, v):
        return _check_theme(v)


class AuthWallResponse(BaseModel):
    id: str
    name: str
    auth_type: str
    session_timeout: int
    theme: str = "default"
    default_provider_id: Optional[str]
    allowed_emails: list[str] = []
    allowed_email_domains: list[str] = []
    local_users: list[LocalAuthUserResponse] = []
    providers: list[AuthProviderResponse] = Field(default=[], validation_alias="auth_providers")
    ldap_config: Optional[LdapConfigResponse] = Field(default=None, validation_alias="ldap_configs")
    proxy_hosts: list[ProxyHostRef] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True

    @field_validator('allowed_emails', 'allowed_email_domains', mode='before')
    @classmethod
    def none_is_empty(cls, v):
        return v or []

    @computed_field
    @property
    def oauth_open_to_anyone(self) -> bool:
        """An enabled Google/GitHub/OIDC provider with no allow-list admits any account."""
        return open_to_any_account(self, self.providers)

    @field_validator('ldap_config', mode='before')
    @classmethod
    def extract_first_ldap(cls, v):
        """Extract first LDAP config from list (frontend expects single object)"""
        if isinstance(v, list):
            return v[0] if v else None
        return v
