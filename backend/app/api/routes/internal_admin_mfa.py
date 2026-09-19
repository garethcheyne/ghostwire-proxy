"""Admin two-factor checks for the admin UI's sign-in (Better Auth).

The UI signs people in with Better Auth; before it creates a session for someone with two-factor
(or while two-factor is required and they haven't set it up), its plugin calls these endpoints.
They reuse admin_mfa_service, so secrets, backup codes and the org-wide policy stay as they were.

Internal only: every call needs the X-Internal-Auth token (the UI container has it).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.internal import verify_internal_auth
from app.core.database import get_db
from app.models.user import User
from app.services import admin_mfa_service

router = APIRouter(dependencies=[Depends(verify_internal_auth)])


class UserRequest(BaseModel):
    user_id: str


class CodeRequest(BaseModel):
    user_id: str
    code: str


async def _active_user(db: AsyncSession, user_id: str) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found or disabled")
    return user


@router.post("/state")
async def mfa_state(body: UserRequest, db: AsyncSession = Depends(get_db)):
    """What sign-in still needs: a code ('totp'), enrolment ('enrol'), or nothing ('none')."""
    user = await _active_user(db, body.user_id)
    if admin_mfa_service.is_enrolled(user):
        return {"required": "totp"}
    if await admin_mfa_service.is_mfa_required(db):
        return {"required": "enrol"}
    return {"required": "none"}


@router.post("/verify")
async def verify_code(body: CodeRequest, db: AsyncSession = Depends(get_db)):
    """Checks a TOTP or backup code (a backup code is used up)."""
    user = await _active_user(db, body.user_id)
    ok = await admin_mfa_service.verify_code(db, user, body.code)
    remaining = await admin_mfa_service.remaining_backup_codes(user) if ok else None
    return {"ok": ok, "backup_codes_remaining": remaining}


@router.post("/enrol/begin")
async def begin_enrolment(body: UserRequest, db: AsyncSession = Depends(get_db)):
    """Forced enrolment at sign-in: a new secret, QR code and backup codes (not live yet)."""
    user = await _active_user(db, body.user_id)
    if admin_mfa_service.is_enrolled(user):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Two-factor is already enabled")
    try:
        result = await admin_mfa_service.begin_enrolment(db, user)
    except admin_mfa_service.MfaNotAvailable as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    return {
        "secret": result["secret"],
        "provisioning_uri": result["provisioning_uri"],
        "qr_code": admin_mfa_service.build_qr_data_uri(result["provisioning_uri"]),
        "backup_codes": result["backup_codes"],
    }


@router.post("/enrol/confirm")
async def confirm_enrolment(body: CodeRequest, db: AsyncSession = Depends(get_db)):
    """Turns two-factor on once the user proves their app generates codes."""
    user = await _active_user(db, body.user_id)
    try:
        ok = await admin_mfa_service.confirm_enrolment(db, user, body.code)
    except admin_mfa_service.MfaNotAvailable as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    return {"ok": ok}
