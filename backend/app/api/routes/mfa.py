"""Admin portal two-factor authentication management.

Enrolment is a three-step handshake:

    POST /api/auth/mfa/setup    -> secret + QR + backup codes (nothing enforced yet)
    POST /api/auth/mfa/verify   -> user proves they can generate a code; MFA goes live
    POST /api/auth/mfa/disable  -> requires password *and* a current code

`setup` and `verify` accept an enrolment token as well as a session token, so a
user caught by the org-wide requirement can complete enrolment before they have
a session. Everything else here needs a real session.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limiter import limiter, RATE_LIMITS
from app.core.security import verify_password
from app.core.utils import get_client_ip
from app.models.audit_log import AuditLog
from app.models.user import User
from app.api.deps import get_current_user, get_current_admin_user, get_enrolling_user
from app.schemas.auth import (
    MfaStatusResponse,
    MfaSetupResponse,
    MfaVerifyRequest,
    MfaVerifiedResponse,
    MfaDisableRequest,
    BackupCodesResponse,
)
from app.services import admin_mfa_service

router = APIRouter()


async def _audit(db: AsyncSession, request: Request, user: User, action: str, details: str = None):
    db.add(AuditLog(
        user_id=user.id,
        email=user.email,
        action=action,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        details=details,
    ))
    await db.commit()


@router.get("/status", response_model=MfaStatusResponse)
async def mfa_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current user's MFA state, plus whether the org requires it."""
    return MfaStatusResponse(
        enabled=bool(current_user.totp_enabled),
        verified=bool(current_user.totp_verified),
        enrolled_at=current_user.totp_enrolled_at.isoformat() if current_user.totp_enrolled_at else None,
        backup_codes_remaining=await admin_mfa_service.remaining_backup_codes(current_user),
        required_org_wide=await admin_mfa_service.is_mfa_required(db),
    )


@router.post("/setup", response_model=MfaSetupResponse)
@limiter.limit(RATE_LIMITS["auth"])
async def setup_mfa(
    request: Request,
    current_user: User = Depends(get_enrolling_user),
    db: AsyncSession = Depends(get_db),
):
    """Begin enrolment: mint a secret, QR code and backup codes.

    Calling this again before verifying replaces the pending secret, which is
    how someone recovers from a half-finished setup. It refuses to clobber an
    already-active secret — disable first, so an open session can't silently
    swap the second factor for one the attacker controls.
    """
    if admin_mfa_service.is_enrolled(current_user):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Two-factor authentication is already enabled. Disable it first to re-enrol.",
        )

    try:
        result = await admin_mfa_service.begin_enrolment(db, current_user)
    except admin_mfa_service.MfaNotAvailable as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    await _audit(db, request, current_user, "mfa_setup_started")

    return MfaSetupResponse(
        secret=result["secret"],
        provisioning_uri=result["provisioning_uri"],
        qr_code=admin_mfa_service.build_qr_data_uri(result["provisioning_uri"]),
        backup_codes=result["backup_codes"],
    )


@router.post("/verify", response_model=MfaVerifiedResponse)
@limiter.limit(RATE_LIMITS["auth"])
async def verify_mfa(
    verify_request: MfaVerifyRequest,
    request: Request,
    current_user: User = Depends(get_enrolling_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm enrolment with the first generated code.

    If the caller got here with an enrolment token (forced enrolment at login),
    a successful verification also completes that login — otherwise they would
    have to enter their password again immediately.
    """
    try:
        ok = await admin_mfa_service.confirm_enrolment(db, current_user, verify_request.code)
    except admin_mfa_service.MfaNotAvailable as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))

    if not ok:
        await _audit(db, request, current_user, "mfa_setup_failed", "Invalid code during enrolment")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That code didn't match. Check your device's clock and try again.",
        )

    await _audit(db, request, current_user, "mfa_enabled")

    # Complete the pending login for the forced-enrolment path.
    from app.api.routes.auth import _issue_session

    session = _issue_session(current_user)
    return MfaVerifiedResponse(
        success=True,
        message="Two-factor authentication is now enabled.",
        access_token=session.access_token,
        refresh_token=session.refresh_token,
    )


@router.post("/disable", response_model=MfaVerifiedResponse)
@limiter.limit(RATE_LIMITS["auth"])
async def disable_mfa(
    disable_request: MfaDisableRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Turn MFA off. Requires the password *and* a current code."""
    if await admin_mfa_service.is_mfa_required(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Two-factor authentication is required for all admin accounts and cannot be disabled.",
        )

    if not admin_mfa_service.is_enrolled(current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled.",
        )

    if not verify_password(disable_request.password, current_user.password_hash):
        await _audit(db, request, current_user, "mfa_disable_failed", "Invalid password")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")

    if not await admin_mfa_service.verify_code(db, current_user, disable_request.code):
        await _audit(db, request, current_user, "mfa_disable_failed", "Invalid code")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code")

    await admin_mfa_service.disable_mfa(db, current_user)
    await _audit(db, request, current_user, "mfa_disabled")

    return MfaVerifiedResponse(success=True, message="Two-factor authentication disabled.")


@router.post("/backup-codes/regenerate", response_model=BackupCodesResponse)
@limiter.limit(RATE_LIMITS["auth"])
async def regenerate_backup_codes(
    verify_request: MfaVerifyRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Issue a fresh set of backup codes, invalidating the old ones.

    Requires a current TOTP code specifically (not a backup code) — otherwise a
    single leaked backup code could be traded for ten fresh ones.
    """
    if not admin_mfa_service.is_enrolled(current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is not enabled.",
        )

    code = (verify_request.code or "").strip()
    if len(code) == admin_mfa_service.BACKUP_CODE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use a code from your authenticator app, not a backup code.",
        )

    if not await admin_mfa_service.verify_code(db, current_user, code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid verification code")

    codes = await admin_mfa_service.regenerate_backup_codes(db, current_user)
    await _audit(db, request, current_user, "mfa_backup_codes_regenerated")

    return BackupCodesResponse(backup_codes=codes)


@router.get("/policy")
async def get_mfa_policy(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Org-wide MFA requirement, plus who has and hasn't enrolled."""
    from sqlalchemy import select

    users = (await db.execute(select(User).where(User.is_active == True))).scalars().all()
    enrolled = [u for u in users if admin_mfa_service.is_enrolled(u)]

    return {
        "required": await admin_mfa_service.is_mfa_required(db),
        "total_active_users": len(users),
        "enrolled_count": len(enrolled),
        "not_enrolled": [
            {"id": u.id, "email": u.email, "name": u.name, "role": u.role}
            for u in users if not admin_mfa_service.is_enrolled(u)
        ],
    }


@router.put("/policy")
async def set_mfa_policy(
    payload: dict,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Turn the org-wide requirement on or off.

    Enabling it while you yourself are not enrolled is refused: it would take
    effect on your own next login, and a bad interaction there locks every admin
    out of the portal. Enrol first, then require it of everyone else.
    """
    required = bool(payload.get("required"))

    if required and not admin_mfa_service.is_enrolled(current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enable two-factor authentication on your own account before requiring it for everyone.",
        )

    await admin_mfa_service.set_mfa_required(db, required)
    await _audit(
        db, request, current_user,
        "mfa_policy_changed",
        f"Org-wide MFA requirement {'enabled' if required else 'disabled'}",
    )

    return {"required": required}
