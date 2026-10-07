"""Settings > API keys.

Admin session only: a key can never list, mint or revoke keys (api_key_service marks this whole
router session-only). Creating a key needs the admin's current two-factor code, as disabling
two-factor and regenerating backup codes do.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin_user
from app.core.database import get_db
from app.core.rate_limiter import RATE_LIMITS, limiter
from app.core.utils import get_client_ip
from app.models.api_key import ApiKey
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyResponse, ApiKeyScope
from app.services import admin_mfa_service, api_key_service

router = APIRouter()


def _view(key: ApiKey, emails: dict[str, str]) -> dict:
    return {
        "id": key.id,
        "name": key.name,
        "prefix": key.prefix,
        "display": f"{api_key_service.KEY_PREFIX}{key.prefix}_…",
        "scopes": list(key.scopes or []),
        "created_by": key.created_by,
        "created_by_email": emails.get(key.created_by),
        "created_at": key.created_at,
        "last_used_at": key.last_used_at,
        "last_used_ip": key.last_used_ip,
        "expires_at": key.expires_at,
        "revoked_at": key.revoked_at,
        "status": api_key_service.key_status(key),
    }


def _audit(db: AsyncSession, request: Request, user: User, action: str, details: str) -> None:
    db.add(AuditLog(
        user_id=user.id,
        email=user.email,
        action=action,
        details=details,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    ))


@router.get("/scopes", response_model=list[ApiKeyScope])
async def list_scopes(current_user: User = Depends(get_current_admin_user)):
    """The scopes a key can carry, with what each allows."""
    return [{"name": name, "description": text} for name, text in api_key_service.SCOPES.items()]


@router.get("/", response_model=list[ApiKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Every key on this instance (any admin can see and revoke any key)."""
    keys = (await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))).scalars().all()
    owner_ids = {k.created_by for k in keys}
    emails: dict[str, str] = {}
    if owner_ids:
        rows = await db.execute(select(User.id, User.email).where(User.id.in_(owner_ids)))
        emails = {row.id: row.email for row in rows}
    return [_view(k, emails) for k in keys]


@router.post("/", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
@limiter.limit(RATE_LIMITS["auth"])
async def create_api_key(
    payload: ApiKeyCreate,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Mint a key. The full key is in this response and nowhere else, ever."""
    if not admin_mfa_service.is_enrolled(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Turn on two-factor authentication for your account (Settings) before creating API keys.",
        )
    if not await admin_mfa_service.verify_code(db, current_user, payload.code):
        _audit(db, request, current_user, "api_key_create_failed", "Invalid two-factor code")
        await db.commit()
        # 400, not 401: the admin UI treats any 401 as "session expired" and signs out.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")

    try:
        row, key = await api_key_service.create_key(
            db, current_user, payload.name, payload.scopes, payload.expires_in_days,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    _audit(
        db, request, current_user, "api_key_created",
        f"Created API key '{row.name}' (gwp_{row.prefix}) with scopes: {', '.join(row.scopes)}",
    )
    await db.commit()

    return {**_view(row, {current_user.id: current_user.email}), "key": key}


@router.delete("/{key_id}", response_model=ApiKeyResponse)
async def revoke_api_key(
    key_id: str,
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a key. It stops working at once; the row stays so the audit log can name it."""
    row = (await db.execute(select(ApiKey).where(ApiKey.id == key_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        _audit(db, request, current_user, "api_key_revoked", f"Revoked API key '{row.name}' (gwp_{row.prefix})")
        await db.commit()

    owner = (await db.execute(select(User.email).where(User.id == row.created_by))).scalar_one_or_none()
    return _view(row, {row.created_by: owner} if owner else {})
