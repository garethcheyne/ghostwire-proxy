from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime
from typing import Optional


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
class AuthWallBase(BaseModel):
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


class AuthWallCreate(AuthWallBase):
    local_users: Optional[list[LocalAuthUserCreate]] = None
    auth_providers: Optional[list[AuthProviderCreate]] = None
    ldap_configs: Optional[list[LdapConfigCreate]] = None


class AuthWallUpdate(BaseModel):
    name: Optional[str] = None
    auth_type: Optional[str] = None
    session_timeout: Optional[int] = None
    theme: Optional[str] = None
    default_provider_id: Optional[str] = None


class AuthWallResponse(BaseModel):
    id: str
    name: str
    auth_type: str
    session_timeout: int
    theme: str = "default"
    default_provider_id: Optional[str]
    local_users: list[LocalAuthUserResponse] = []
    providers: list[AuthProviderResponse] = Field(default=[], validation_alias="auth_providers")
    ldap_config: Optional[LdapConfigResponse] = Field(default=None, validation_alias="ldap_configs")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True

    @field_validator('ldap_config', mode='before')
    @classmethod
    def extract_first_ldap(cls, v):
        """Extract first LDAP config from list (frontend expects single object)"""
        if isinstance(v, list):
            return v[0] if v else None
        return v
