"""Admin sign-in with Better Auth, as seen from the API.

Better Auth (in the admin UI) signs people in and stores their session in `auth_session`. Its
cookie holds `<token>.<signature>`, the signature being base64(HMAC-SHA256(secret, token)). The
API accepts that cookie, or the bare token as `Authorization: Bearer <token>` (scripts, tests).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models.auth import AuthAccount, AuthSession

# Matches advanced.cookiePrefix in frontend/src/lib/auth.ts. Browsers get the __Secure- form on https.
COOKIE_NAMES = ("__Secure-gwp.session_token", "gwp.session_token")
SESSION_DAYS = 7


def sign(token: str, secret: str | None = None) -> str:
    key = (secret if secret is not None else settings.better_auth_secret).encode()
    digest = hmac.new(key, token.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def token_from_cookie(value: str | None) -> str | None:
    """The session token from a signed cookie value, or None if the signature is wrong."""
    if not value:
        return None
    value = unquote(value)
    token, dot, signature = value.rpartition(".")
    if not dot or not token or not signature:
        return None
    if not settings.better_auth_secret:
        return None
    return token if hmac.compare_digest(sign(token), signature) else None


async def find_session(db: AsyncSession, token: str) -> AuthSession | None:
    result = await db.execute(
        select(AuthSession).where(
            AuthSession.token == token,
            AuthSession.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()


async def create_session(
    db: AsyncSession, user_id: str, ip_address: str | None = None, user_agent: str | None = None
) -> AuthSession:
    """A session as Better Auth would create it (used by tests and scripts)."""
    session = AuthSession(
        user_id=user_id,
        token=secrets.token_urlsafe(24),
        expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(session)
    await db.flush()
    return session


async def revoke_sessions(db: AsyncSession, user_id: str) -> None:
    await db.execute(delete(AuthSession).where(AuthSession.user_id == user_id))


async def set_password(db: AsyncSession, user, password: str) -> None:
    """Sets a user's sign-in password (their 'credential' account) and the legacy hash."""
    password_hash = get_password_hash(password)
    user.password_hash = password_hash

    result = await db.execute(
        update(AuthAccount)
        .where(AuthAccount.user_id == user.id, AuthAccount.provider_id == "credential")
        .values(password=password_hash, updated_at=datetime.now(timezone.utc))
    )
    if result.rowcount == 0:
        db.add(
            AuthAccount(
                user_id=user.id,
                account_id=user.id,
                provider_id="credential",
                password=password_hash,
            )
        )


async def verify_user_password(db: AsyncSession, user, password: str) -> bool:
    """Checks a user's sign-in password (their 'credential' account, as Better Auth does)."""
    stored = (
        await db.execute(
            select(AuthAccount.password).where(
                AuthAccount.user_id == user.id, AuthAccount.provider_id == "credential"
            )
        )
    ).scalar_one_or_none() or user.password_hash
    return bool(stored) and verify_password(password, stored)


async def delete_auth_data(db: AsyncSession, user_id: str) -> None:
    await revoke_sessions(db, user_id)
    await db.execute(delete(AuthAccount).where(AuthAccount.user_id == user_id))
