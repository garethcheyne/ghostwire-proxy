from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.auth_session import COOKIE_NAMES, find_session, token_from_cookie
from app.core.database import get_db
from app.core.utils import get_client_ip
from app.models.user import User
from app.services import api_key_service


def _bearer(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() == "bearer" and credentials.strip():
        return credentials.strip()
    return None


async def _api_key_user(request: Request, db: AsyncSession, token: str) -> User:
    """Authenticate `Authorization: Bearer gwp_...` and check the key's scope for this route.

    The scope a route needs comes from its method and path (api_key_service.required_scope), so
    no route has to opt in and anything unlisted is refused to keys. Route-level role checks
    (get_current_admin_user) still apply on top, as the key acts as the admin who created it.
    """
    client_ip = get_client_ip(request)
    try:
        principal = await api_key_service.authenticate(db, token, client_ip)
        scope = api_key_service.check_request_scope(principal, request.method, request.url.path)
    except api_key_service.ApiKeyError as e:
        headers = {"WWW-Authenticate": "Bearer"} if e.status_code == 401 else None
        raise HTTPException(status_code=e.status_code, detail=e.detail, headers=headers)

    request.state.api_key = principal
    # Changes are audited; reads and dry-run previews (scope "read") are not.
    if scope != api_key_service.READ:
        await api_key_service.record_use(
            db, principal, request.method.upper(), request.url.path, client_ip,
            request.headers.get("user-agent"),
        )
    return principal.user


def _session_token(request: Request) -> str | None:
    """Better Auth's signed session cookie, or its bare token as a Bearer header."""
    for name in COOKIE_NAMES:
        token = token_from_cookie(request.cookies.get(name))
        if token:
            return token

    return _bearer(request)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    bearer = _bearer(request)
    if api_key_service.looks_like_key(bearer):
        return await _api_key_user(request, db, bearer)

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
