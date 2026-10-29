"""
Schemas for Auth Wall Session management.
"""

from datetime import datetime

from pydantic import BaseModel


# Session validation (for Lua internal API)
class SessionValidateRequest(BaseModel):
    """Request from Lua to validate a session."""

    session_id: str
    auth_wall_id: str
    signature: str


class SessionValidateResponse(BaseModel):
    """Response to Lua with session validation result."""

    valid: bool
    session_id: str | None = None
    auth_wall_id: str | None = None
    user_type: str | None = None
    user_id: str | None = None
    username: str | None = None
    email: str | None = None
    display_name: str | None = None
    expires_at: int | None = None  # Unix timestamp for Lua


# Session info for admin UI
class SessionResponse(BaseModel):
    """Full session info for admin viewing."""

    id: str
    auth_wall_id: str
    user_type: str
    user_id: str
    username: str
    email: str | None
    display_name: str | None
    provider_id: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    expires_at: datetime
    last_activity_at: datetime
    revoked: bool
    revoked_at: datetime | None
    revoked_reason: str | None

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    """Paginated list of sessions."""

    sessions: list[SessionResponse]
    total: int
    page: int
    per_page: int


class SessionRevokeRequest(BaseModel):
    """Request to revoke a session."""

    reason: str | None = None


class SessionRevokeAllRequest(BaseModel):
    """Request to revoke all sessions for a user."""

    user_id: str | None = None  # If None, revoke all sessions for the auth wall
    reason: str | None = None


# Auth wall config for Lua
class AuthWallConfigProvider(BaseModel):
    """Provider info for Lua."""

    id: str
    name: str
    provider_type: str
    enabled: bool


class AuthWallConfigResponse(BaseModel):
    """Auth wall configuration returned to Lua and frontend auth portal."""

    id: str
    name: str
    auth_type: str
    session_timeout: int
    theme: str = "default"  # Auth portal theme directory
    providers: list[AuthWallConfigProvider] = []
    has_local_users: bool = False
    has_ldap: bool = False


# Login request/response
class LocalLoginRequest(BaseModel):
    """Login request for local auth."""

    username: str
    password: str


class LocalLoginResponse(BaseModel):
    """Login response - may require TOTP."""

    success: bool
    requires_totp: bool = False
    partial_session_id: str | None = None  # Used to continue TOTP flow
    session_cookie: str | None = None  # Set if login complete
    message: str = ""


class TotpLoginRequest(BaseModel):
    """Complete login with TOTP code."""

    partial_session_id: str
    code: str
    is_backup_code: bool = False


class OAuthStartResponse(BaseModel):
    """Response when starting OAuth flow."""

    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    """OAuth callback parameters."""

    code: str
    state: str


class OAuthCallbackResponse(BaseModel):
    """OAuth callback result."""

    success: bool
    session_cookie: str | None = None
    redirect_url: str | None = None
    error: str | None = None


# Session creation (internal)
class SessionCreateRequest(BaseModel):
    """Internal request to create a session."""

    auth_wall_id: str
    user_type: str
    user_id: str
    username: str
    email: str | None = None
    display_name: str | None = None
    provider_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None


class SessionCreateResponse(BaseModel):
    """Internal response with created session."""

    session_id: str
    session_cookie: str  # Signed cookie value: {session_id}.{signature}
    expires_at: datetime
