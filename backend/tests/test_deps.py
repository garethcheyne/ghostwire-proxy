"""Tests for deps module — sign-in through Better Auth sessions."""

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.deps import get_current_user, get_current_admin_user
from app.core.auth_session import create_session, sign


def make_request(cookies: dict[str, str] | None = None, bearer: str | None = None) -> Request:
    headers = []
    if cookies:
        headers.append((b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()))
    if bearer:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def cookie_value(token: str) -> str:
    """What Better Auth puts in the cookie: url-encoded `token.signature`."""
    return quote(f"{token}.{sign(token)}", safe="")


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_signed_cookie_returns_user(self, db_session, admin_user):
        session = await create_session(db_session, admin_user.id)
        await db_session.commit()

        request = make_request(cookies={"gwp.session_token": cookie_value(session.token)})
        user = await get_current_user(request=request, db=db_session)
        assert user.id == admin_user.id

    @pytest.mark.asyncio
    async def test_secure_cookie_name_on_https(self, db_session, admin_user):
        session = await create_session(db_session, admin_user.id)
        await db_session.commit()

        request = make_request(cookies={"__Secure-gwp.session_token": cookie_value(session.token)})
        user = await get_current_user(request=request, db=db_session)
        assert user.id == admin_user.id

    @pytest.mark.asyncio
    async def test_bearer_session_token_returns_user(self, db_session, admin_user):
        session = await create_session(db_session, admin_user.id)
        await db_session.commit()

        user = await get_current_user(request=make_request(bearer=session.token), db=db_session)
        assert user.id == admin_user.id

    @pytest.mark.asyncio
    async def test_forged_signature_rejected(self, db_session, admin_user):
        session = await create_session(db_session, admin_user.id)
        await db_session.commit()

        forged = quote(f"{session.token}.{sign(session.token, 'another-secret')}", safe="")
        with pytest.raises(HTTPException) as exc:
            await get_current_user(
                request=make_request(cookies={"gwp.session_token": forged}), db=db_session
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_token_rejected(self, db_session):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request=make_request(bearer="not-a-session"), db=db_session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_credentials_rejected(self, db_session):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(request=make_request(), db=db_session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_session_rejected(self, db_session, admin_user):
        session = await create_session(db_session, admin_user.id)
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc:
            await get_current_user(request=make_request(bearer=session.token), db=db_session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_deleted_user_rejected(self, db_session):
        session = await create_session(db_session, "deleted-user-id")
        await db_session.commit()

        with pytest.raises(HTTPException) as exc:
            await get_current_user(request=make_request(bearer=session.token), db=db_session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_user_rejected(self, db_session, inactive_user):
        session = await create_session(db_session, inactive_user.id)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc:
            await get_current_user(request=make_request(bearer=session.token), db=db_session)
        assert exc.value.status_code == 403


class TestGetCurrentAdminUser:
    @pytest.mark.asyncio
    async def test_admin_user_passes(self, admin_user):
        result = await get_current_admin_user(current_user=admin_user)
        assert result.role == "admin"

    @pytest.mark.asyncio
    async def test_non_admin_raises(self, regular_user):
        with pytest.raises(HTTPException) as exc:
            await get_current_admin_user(current_user=regular_user)
        assert exc.value.status_code == 403
        assert "Admin" in exc.value.detail
