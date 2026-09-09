from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
from typing import Union

from app.core.database import get_db
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token
from app.core.rate_limiter import limiter, RATE_LIMITS
from app.core.utils import get_client_ip
from app.models.user import User
from app.models.audit_log import AuditLog
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    LoginChallengeResponse,
    TotpLoginRequest,
)
from app.schemas.user import UserResponse
from app.api.deps import get_current_user
from app.services import admin_mfa_service
from jose import jwt as _jwt

router = APIRouter()

# A challenge token is only good for the few minutes between "password accepted"
# and "second factor supplied". Short enough that a leaked one is near-useless,
# long enough to fetch a code from a phone.
MFA_CHALLENGE_MINUTES = 5
# Enrolment is a longer interaction — install an app, scan, save backup codes.
MFA_ENROLMENT_MINUTES = 15


def _issue_session(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(data={"sub": str(user.id)}),
        refresh_token=create_refresh_token(data={"sub": str(user.id)}),
    )


def _create_scoped_token(user: User, token_type: str, minutes: int) -> str:
    """Mint a non-session token. `type` is anything but "access", so
    `get_current_user` will refuse it."""
    from app.core.config import settings as _settings

    payload = {
        "sub": str(user.id),
        "type": token_type,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
    }
    return _jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


async def _log_auth_event(
    db: AsyncSession,
    request: Request,
    user: User | None,
    email: str,
    action: str,
    details: str | None = None,
) -> None:
    db.add(AuditLog(
        user_id=user.id if user else None,
        email=email,
        action=action,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=details,
    ))
    await db.commit()


@router.post("/login", response_model=Union[TokenResponse, LoginChallengeResponse])
@limiter.limit(RATE_LIMITS["auth"])
async def login(
    login_request: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return JWT tokens.

    Returns a `LoginChallengeResponse` instead of a session when a second factor
    is outstanding — either because the user is enrolled in TOTP, or because MFA
    is required org-wide and they have not enrolled yet.
    """
    # Find user by email
    result = await db.execute(
        select(User).where(User.email == login_request.email.lower())
    )
    user = result.scalar_one_or_none()

    # Verify credentials
    if not user or not verify_password(login_request.password, user.password_hash):
        await _log_auth_event(
            db, request, user, login_request.email, "login_failed", "Invalid credentials"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Password is correct, but it may not be sufficient on its own.
    if admin_mfa_service.is_enrolled(user):
        await _log_auth_event(
            db, request, user, user.email, "login_mfa_challenged",
            "Password accepted, awaiting TOTP",
        )
        return LoginChallengeResponse(
            challenge="totp",
            challenge_token=_create_scoped_token(user, "mfa_challenge", MFA_CHALLENGE_MINUTES),
            message="Enter the 6-digit code from your authenticator app",
        )

    if await admin_mfa_service.is_mfa_required(db):
        # Org-wide requirement, not yet satisfied. Hand back only an enrolment
        # token — no session until they finish setting up.
        await _log_auth_event(
            db, request, user, user.email, "login_mfa_enrolment_required",
            "MFA required org-wide; user not enrolled",
        )
        return LoginChallengeResponse(
            challenge="enrol",
            enrolment_token=_create_scoped_token(user, "mfa_enrol", MFA_ENROLMENT_MINUTES),
            message="Two-factor authentication is required. Set it up to continue.",
        )

    # Update user login stats
    user.signin_count += 1
    user.last_signin_at = datetime.now(timezone.utc)

    await _log_auth_event(db, request, user, user.email, "login_success")

    return _issue_session(user)


@router.post("/login/totp", response_model=TokenResponse)
@limiter.limit(RATE_LIMITS["auth"])
async def login_totp(
    totp_request: TotpLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Complete a login by supplying the second factor.

    Rate-limited on the same bucket as password login, so a stolen challenge
    token can't be used to brute-force the 6-digit space.
    """
    payload = decode_token(totp_request.challenge_token)
    if not payload or payload.get("type") != "mfa_challenge":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login session expired. Please sign in again.",
        )

    result = await db.execute(select(User).where(User.id == payload.get("sub")))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login session expired. Please sign in again.",
        )

    if not await admin_mfa_service.verify_code(db, user, totp_request.code):
        await _log_auth_event(
            db, request, user, user.email, "login_mfa_failed", "Invalid TOTP or backup code"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code",
        )

    user.signin_count += 1
    user.last_signin_at = datetime.now(timezone.utc)

    remaining = await admin_mfa_service.remaining_backup_codes(user)
    await _log_auth_event(
        db, request, user, user.email, "login_success",
        f"Second factor verified ({remaining} backup codes remaining)",
    )

    return _issue_session(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token using refresh token"""
    payload = decode_token(refresh_request.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Create new tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    new_refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current authenticated user info"""
    return current_user


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logout current user (audit log only, token invalidation is client-side)"""
    audit_log = AuditLog(
        user_id=current_user.id,
        email=current_user.email,
        action="logout",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    db.add(audit_log)
    await db.commit()

    return {"message": "Logged out successfully"}
