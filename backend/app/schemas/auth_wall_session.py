"""
Schemas for Auth Wall Session management.
"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# Session validation (for Lua internal API)
class SessionValidateRequest(BaseModel):
    """Request from Lua to validate a session."""
    session_id: str
    auth_wall_id: str
    signature: str


class SessionValidateResponse(BaseModel):
    """Response to Lua with session validation result."""
    valid: bool
    session_id: Optional[str] = None
    auth_wall_id: Optional[str] = None
    user_type: Optional[str] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None
    expires_at: Optional[int] = None  # Unix timestamp for Lua


# Session info for admin UI
class SessionResponse(BaseModel):
    """Full session info for admin viewing."""
    id: str
    auth_wall_id: str
    user_type: str
    user_id: str
    username: str
    email: Optional[str]
    display_name: Optional[str]
    provider_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    expires_at: datetime
    last_activity_at: datetime
    revoked: bool
    revoked_at: Optional[datetime]
    revoked_reason: Optional[str]

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
    reason: Optional[str] = None


class SessionRevokeAllRequest(BaseModel):
    """Request to revoke all sessions for a user."""
    user_id: Optional[str] = None  # If None, revoke all sessions for the auth wall
    reason: Optional[str] = None


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
    partial_session_id: Optional[str] = None  # Used to continue TOTP flow
    session_cookie: Optional[str] = None  # Set if login complete
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
    session_cookie: Optional[str] = None
    redirect_url: Optional[str] = None
    error: Optional[str] = None


# Session creation (internal)
class SessionCreateRequest(BaseModel):
    """Internal request to create a session."""
    auth_wall_id: str
    user_type: str
    user_id: str
    username: str
    email: Optional[str] = None
    display_name: Optional[str] = None
    provider_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class SessionCreateResponse(BaseModel):
    """Internal response with created session."""
    session_id: str
    session_cookie: str  # Signed cookie value: {session_id}.{signature}
    expires_at: datetime
