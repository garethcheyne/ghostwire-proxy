"""
Auth Portal API routes.
Handles login, logout, OAuth callbacks, and TOTP verification for auth walls.
These endpoints are accessed via /__auth/* paths through nginx.
"""
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel

from app.core.database import get_db
from app.core.redis import get_redis
from app.core.utils import get_client_ip
from app.services.auth_portal_redirect import safe_redirect_target, request_origin
from app.services.auth_wall_access import is_email_allowed
from app.models.auth_wall import AuthWall, LocalAuthUser, AuthProvider
from app.models.audit_log import AuditLog
from app.services.session_service import SessionService, get_cookie_header, get_clear_cookie_header
from app.services.auth_providers import ProviderFactory, LocalAuthProvider
from app.schemas.auth_wall_session import (
    LocalLoginRequest,
    LocalLoginResponse,
    TotpLoginRequest,
    OAuthStartResponse,
    OAuthCallbackRequest,
    OAuthCallbackResponse,
    AuthWallConfigResponse,
    AuthWallConfigProvider,
)

router = APIRouter()

# Redis key prefixes for OAuth state and partial sessions
_OAUTH_STATE_PREFIX = "oauth_state:"
_PARTIAL_SESSION_PREFIX = "partial_session:"
# Wrong TOTP codes allowed per password sign-in before it has to start over
_MAX_TOTP_ATTEMPTS = 5


async def _set_oauth_state(state: str, data: dict, ttl_seconds: int = 600):
    """Store OAuth state in Redis with TTL."""
    r = await get_redis()
    data_copy = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in data.items()}
    await r.setex(f"{_OAUTH_STATE_PREFIX}{state}", ttl_seconds, json.dumps(data_copy))


async def _get_oauth_state(state: str) -> Optional[dict]:
    """Get OAuth state from Redis."""
    r = await get_redis()
    raw = await r.get(f"{_OAUTH_STATE_PREFIX}{state}")
    if not raw:
        return None
    data = json.loads(raw)
    if "expires_at" in data:
        data["expires_at"] = datetime.fromisoformat(data["expires_at"])
    return data


async def _del_oauth_state(state: str):
    """Delete OAuth state from Redis."""
    r = await get_redis()
    await r.delete(f"{_OAUTH_STATE_PREFIX}{state}")


async def _set_partial_session(partial_id: str, data: dict, ttl_seconds: int = 300):
    """Store partial session in Redis with TTL."""
    r = await get_redis()
    data_copy = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in data.items()}
    await r.setex(f"{_PARTIAL_SESSION_PREFIX}{partial_id}", ttl_seconds, json.dumps(data_copy))


async def _get_partial_session(partial_id: str) -> Optional[dict]:
    """Get partial session from Redis."""
    r = await get_redis()
    raw = await r.get(f"{_PARTIAL_SESSION_PREFIX}{partial_id}")
    if not raw:
        return None
    data = json.loads(raw)
    if "expires_at" in data:
        data["expires_at"] = datetime.fromisoformat(data["expires_at"])
    return data


async def _del_partial_session(partial_id: str):
    """Delete partial session from Redis."""
    r = await get_redis()
    await r.delete(f"{_PARTIAL_SESSION_PREFIX}{partial_id}")


@router.get("/{auth_wall_id}/config", response_model=AuthWallConfigResponse)
async def get_auth_wall_config(
    auth_wall_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get auth wall configuration for login page."""
    result = await db.execute(
        select(AuthWall)
        .options(
            selectinload(AuthWall.auth_providers),
            selectinload(AuthWall.local_users),
            selectinload(AuthWall.ldap_configs),
        )
        .where(AuthWall.id == auth_wall_id)
    )
    auth_wall = result.scalar_one_or_none()

    if not auth_wall:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth wall not found",
        )

    providers = [
        AuthWallConfigProvider(
            id=p.id,
            name=p.name,
            provider_type=p.provider_type,
            enabled=p.enabled,
        )
        for p in auth_wall.auth_providers
        if p.enabled
    ]

    return AuthWallConfigResponse(
        id=auth_wall.id,
        name=auth_wall.name,
        auth_type=auth_wall.auth_type,
        session_timeout=auth_wall.session_timeout,
        providers=providers,
        has_local_users=any(u.is_active for u in auth_wall.local_users),
        has_ldap=any(l.enabled for l in auth_wall.ldap_configs),
    )


@router.post("/{auth_wall_id}/login/local", response_model=LocalLoginResponse)
async def local_login(
    auth_wall_id: str,
    login_data: LocalLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Login with local username/password."""
    # Get auth wall
    result = await db.execute(
        select(AuthWall)
        .options(selectinload(AuthWall.local_users))
        .where(AuthWall.id == auth_wall_id)
    )
    auth_wall = result.scalar_one_or_none()

    if not auth_wall:
        raise HTTPException(status_code=404, detail="Auth wall not found")

    # Find user
    user = next(
        (u for u in auth_wall.local_users if u.username == login_data.username and u.is_active),
        None
    )

    # Get client info for audit
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    if not user:
        # Log failed attempt
        audit = AuditLog(
            action="auth_wall_login_failed",
            ip_address=client_ip,
            user_agent=user_agent,
            details=f"Auth wall: {auth_wall.name}, User not found: {login_data.username}",
        )
        db.add(audit)
        await db.commit()
        return LocalLoginResponse(success=False, message="Invalid username or password")

    # Check if locked
    if user.is_locked():
        return LocalLoginResponse(success=False, message="Account is temporarily locked")

    # Authenticate
    local_provider = LocalAuthProvider(auth_wall=auth_wall, db=db)
    user_info = await local_provider.authenticate({
        "username": login_data.username,
        "password": login_data.password,
    })

    if not user_info:
        # Log failed attempt
        audit = AuditLog(
            action="auth_wall_login_failed",
            ip_address=client_ip,
            user_agent=user_agent,
            details=f"Auth wall: {auth_wall.name}, Invalid password for: {login_data.username}",
        )
        db.add(audit)
        await db.commit()
        return LocalLoginResponse(success=False, message="Invalid username or password")

    # Check if TOTP required
    if local_provider.requires_totp(user):
        # Create partial session for TOTP verification
        partial_id = secrets.token_hex(32)
        await _set_partial_session(partial_id, {
            "user_id": user.id,
            "auth_wall_id": auth_wall_id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
        })
        return LocalLoginResponse(
            success=True,
            requires_totp=True,
            partial_session_id=partial_id,
            message="TOTP verification required",
        )

    # Create full session
    session_service = SessionService(db)
    session, cookie_value = await session_service.create_session(
        auth_wall_id=auth_wall_id,
        user_type="local",
        user_id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # Set cookie with the correct domain
    # Get domain from X-Forwarded-Host or Host header
    domain = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if domain:
        domain = domain.split(":")[0]  # Remove port if present

    cookie_header = get_cookie_header(
        cookie_value=cookie_value,
        session_timeout=auth_wall.session_timeout,
        secure=True,
        domain=domain,
    )
    response.headers["Set-Cookie"] = cookie_header

    # Log success
    audit = AuditLog(
        action="auth_wall_login_success",
        ip_address=client_ip,
        user_agent=user_agent,
        details=f"Auth wall: {auth_wall.name}, User: {user.username}, Provider: local, Domain: {domain}",
    )
    db.add(audit)
    await db.commit()

    return LocalLoginResponse(
        success=True,
        session_cookie=cookie_value,
        message="Login successful",
    )


@router.post("/{auth_wall_id}/login/totp", response_model=LocalLoginResponse)
async def totp_login(
    auth_wall_id: str,
    totp_data: TotpLoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Complete login with TOTP code."""
    # Get partial session from Redis
    partial = await _get_partial_session(totp_data.partial_session_id)
    if not partial or partial["auth_wall_id"] != auth_wall_id:
        return LocalLoginResponse(success=False, message="Invalid or expired session")

    if partial["expires_at"] < datetime.now(timezone.utc):
        await _del_partial_session(totp_data.partial_session_id)
        return LocalLoginResponse(success=False, message="Session expired")

    # Get auth wall and user
    result = await db.execute(
        select(AuthWall)
        .options(selectinload(AuthWall.local_users))
        .where(AuthWall.id == auth_wall_id)
    )
    auth_wall = result.scalar_one_or_none()

    if not auth_wall:
        return LocalLoginResponse(success=False, message="Auth wall not found")

    user = next((u for u in auth_wall.local_users if u.id == partial["user_id"]), None)
    if not user:
        return LocalLoginResponse(success=False, message="User not found")

    # Verify TOTP
    local_provider = LocalAuthProvider(auth_wall=auth_wall, db=db)
    if not await local_provider.verify_totp(user, totp_data.code):
        attempts = int(partial.get("attempts", 0)) + 1
        if attempts >= _MAX_TOTP_ATTEMPTS:
            await _del_partial_session(totp_data.partial_session_id)
            return LocalLoginResponse(success=False, message="Too many invalid codes. Sign in again.")
        partial["attempts"] = attempts
        r = await get_redis()
        ttl = await r.ttl(f"{_PARTIAL_SESSION_PREFIX}{totp_data.partial_session_id}")
        await _set_partial_session(totp_data.partial_session_id, partial, ttl_seconds=max(int(ttl or 0), 1))
        return LocalLoginResponse(success=False, message="Invalid TOTP code")

    # Remove partial session
    await _del_partial_session(totp_data.partial_session_id)

    # Get client info
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    # Create full session
    session_service = SessionService(db)
    session, cookie_value = await session_service.create_session(
        auth_wall_id=auth_wall_id,
        user_type="local",
        user_id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # Set cookie with the correct domain
    domain = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if domain:
        domain = domain.split(":")[0]

    cookie_header = get_cookie_header(
        cookie_value=cookie_value,
        session_timeout=auth_wall.session_timeout,
        secure=True,
        domain=domain,
    )
    response.headers["Set-Cookie"] = cookie_header

    # Log success
    audit = AuditLog(
        action="auth_wall_login_success",
        ip_address=client_ip,
        user_agent=user_agent,
        details=f"Auth wall: {auth_wall.name}, User: {user.username}, Provider: local (with TOTP)",
    )
    db.add(audit)
    await db.commit()

    return LocalLoginResponse(
        success=True,
        session_cookie=cookie_value,
        message="Login successful",
    )


def _callback_url(request: Request, auth_wall_id: str) -> str:
    """Absolute URL the provider sends the browser back to (register it with the provider)."""
    return f"{request_origin(request)}/api/auth-portal/{auth_wall_id}/callback"


def _portal_error(auth_wall_id: str, message: str, redirect_url: str = "/") -> RedirectResponse:
    from urllib.parse import urlencode

    query = urlencode({"wall": auth_wall_id, "error": message, "redirect": redirect_url})
    return RedirectResponse(url=f"/__auth/callback?{query}", status_code=302)


@router.get("/{auth_wall_id}/oauth/{provider_id}/start")
async def start_oauth(
    auth_wall_id: str,
    provider_id: str,
    request: Request,
    redirect: Optional[str] = Query(None),
    redirect_url: Optional[str] = Query(None),
    format: Optional[str] = Query(None, description="'json' returns the URL instead of redirecting"),
    db: AsyncSession = Depends(get_db),
):
    """Start OAuth flow - redirect the browser to the provider."""
    target = safe_redirect_target(redirect or redirect_url or "/", request)

    # Get provider
    result = await db.execute(
        select(AuthProvider).where(
            AuthProvider.id == provider_id,
            AuthProvider.auth_wall_id == auth_wall_id,
            AuthProvider.enabled == True,
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Get OAuth provider
    oauth_provider = ProviderFactory.get_oauth_provider(provider, db)
    if not oauth_provider:
        raise HTTPException(status_code=400, detail="Unsupported provider type")

    callback_url = _callback_url(request, auth_wall_id)

    # Generate state and store in Redis with 10-minute TTL
    state = secrets.token_hex(32)
    await _set_oauth_state(state, {
        "auth_wall_id": auth_wall_id,
        "provider_id": provider_id,
        "redirect_url": target,
        "callback_url": callback_url,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
    })

    auth_url = await oauth_provider.get_authorization_url(
        callback_url=callback_url,
        state=state,
    )

    if format == "json":
        return OAuthStartResponse(authorization_url=auth_url, state=state)
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/{auth_wall_id}/callback")
async def oauth_callback(
    auth_wall_id: str,
    code: str,
    state: str,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth callback."""
    # Validate state from Redis
    state_data = await _get_oauth_state(state)
    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    if state_data["auth_wall_id"] != auth_wall_id:
        raise HTTPException(status_code=400, detail="State mismatch")

    if state_data["expires_at"] < datetime.now(timezone.utc):
        await _del_oauth_state(state)
        raise HTTPException(status_code=400, detail="State expired")

    # Remove used state (one-time use). Checked again: state written by an older build.
    redirect_url = safe_redirect_target(state_data.get("redirect_url") or "/", request)
    provider_id = state_data["provider_id"]
    await _del_oauth_state(state)

    # Get provider
    result = await db.execute(
        select(AuthProvider).where(
            AuthProvider.id == provider_id,
            AuthProvider.auth_wall_id == auth_wall_id,
        )
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Get auth wall
    result = await db.execute(select(AuthWall).where(AuthWall.id == auth_wall_id))
    auth_wall = result.scalar_one_or_none()

    if not auth_wall:
        raise HTTPException(status_code=404, detail="Auth wall not found")

    # Get OAuth provider
    oauth_provider = ProviderFactory.get_oauth_provider(provider, db)
    if not oauth_provider:
        raise HTTPException(status_code=400, detail="Unsupported provider type")

    # Exchange code for user info (same redirect_uri as the authorization request)
    callback_url = state_data.get("callback_url") or _callback_url(request, auth_wall_id)
    try:
        user_info = await oauth_provider.handle_callback(
            code=code,
            state=state,
            callback_url=callback_url,
        )
    except Exception:
        return _portal_error(auth_wall_id, "Sign-in with the provider failed. Try again.", redirect_url)

    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    # Validate user: verified email (provider rules), then the wall's allow-list
    if not await oauth_provider.validate_user(user_info, auth_wall_id) or not is_email_allowed(auth_wall, user_info.email):
        db.add(AuditLog(
            action="auth_wall_login_denied",
            ip_address=client_ip,
            user_agent=user_agent,
            details=f"Auth wall: {auth_wall.name}, Provider: {provider.provider_type}, not on the allow-list: {user_info.email or user_info.username}",
        ))
        await db.commit()
        return _portal_error(auth_wall_id, "This account is not allowed to access this site.", redirect_url)

    # Create session
    session_service = SessionService(db)
    session, cookie_value = await session_service.create_session(
        auth_wall_id=auth_wall_id,
        user_type=provider.provider_type,
        user_id=user_info.user_id,
        username=user_info.username,
        email=user_info.email,
        display_name=user_info.display_name,
        provider_id=provider_id,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # Set cookie with the correct domain
    domain = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if domain:
        domain = domain.split(":")[0]

    cookie_header = get_cookie_header(
        cookie_value=cookie_value,
        session_timeout=auth_wall.session_timeout,
        secure=True,
        domain=domain,
    )
    response.headers["Set-Cookie"] = cookie_header

    # Log success
    audit = AuditLog(
        action="auth_wall_login_success",
        ip_address=client_ip,
        user_agent=user_agent,
        details=f"Auth wall: {auth_wall.name}, User: {user_info.username}, Provider: {provider.provider_type}",
    )
    db.add(audit)
    await db.commit()

    # Redirect to original URL (same site only)
    redirect = RedirectResponse(url=redirect_url, status_code=302)
    redirect.headers["Set-Cookie"] = cookie_header
    return redirect


@router.post("/{auth_wall_id}/logout")
async def logout(
    auth_wall_id: str,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Logout - revoke session and clear cookie."""
    session_service = SessionService(db)

    # Get session from cookie
    cookie_value = request.cookies.get(SessionService.COOKIE_NAME)
    if cookie_value:
        session_id = session_service.verify_session_cookie(cookie_value)
        if session_id:
            # Revoke session
            await session_service.revoke_session(session_id, reason="User logout")

            # Log logout
            client_ip = get_client_ip(request)
            audit = AuditLog(
                action="auth_wall_logout",
                ip_address=client_ip,
                user_agent=request.headers.get("user-agent"),
                details=f"Session: {session_id[:16]}...",
            )
            db.add(audit)
            await db.commit()

    # Clear cookie
    response.headers["Set-Cookie"] = get_clear_cookie_header()

    return {"success": True, "message": "Logged out"}
