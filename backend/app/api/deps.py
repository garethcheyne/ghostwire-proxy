from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.auth_session import COOKIE_NAMES, find_session, token_from_cookie
from app.core.database import get_db
from app.models.user import User


def _session_token(request: Request) -> str | None:
    """Better Auth's signed session cookie, or its bare token as a Bearer header."""
    for name in COOKIE_NAMES:
        token = token_from_cookie(request.cookies.get(name))
        if token:
            return token

    authorization = request.headers.get("authorization", "")
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() == "bearer" and credentials.strip():
        return credentials.strip()
    return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = _session_token(request)
    session = await find_session(db, token) if token else None

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not signed in or session expired",
        )

    result = await db.execute(select(User).where(User.id == session.user_id))
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

    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def get_enrolling_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """A signed-in user setting up two-factor from the settings page.

    Forced enrolment at sign-in (MFA required org-wide, user not enrolled) has no session yet; the
    admin UI's Better Auth plugin runs it through /api/internal/admin-mfa/* instead.
    """
    return current_user
