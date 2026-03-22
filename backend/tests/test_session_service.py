"""Tests for session service — cookie creation, session management."""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

from app.services.session_service import (
    SessionService,
    get_cookie_header,
    get_clear_cookie_header,
)
from app.models.auth_wall_session import AuthWallSession
from app.models.auth_wall import AuthWall


class TestSessionService:
    """Tests for session CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_session(self, db_session):
        # First create an auth wall
        auth_wall = AuthWall(
            id="wall-1",
            name="Test Wall",
            auth_type="local",
            session_timeout=3600,
        )
        db_session.add(auth_wall)
        await db_session.commit()

        svc = SessionService(db_session)
        session, cookie = await svc.create_session(
            auth_wall_id="wall-1",
            user_type="local",
            user_id="user-1",
            username="testuser",
            email="test@example.com",
            ip_address="127.0.0.1",
        )

        assert session is not None
        assert session.auth_wall_id == "wall-1"
        assert session.username == "testuser"
        assert cookie is not None

    @pytest.mark.asyncio
    async def test_validate_session(self, db_session):
        auth_wall = AuthWall(
            id="wall-2",
            name="Test Wall 2",
            auth_type="local",
            session_timeout=3600,
        )
        db_session.add(auth_wall)
        await db_session.commit()

        svc = SessionService(db_session)
        session, cookie = await svc.create_session(
            auth_wall_id="wall-2",
            user_type="local",
            user_id="user-2",
            username="testuser2",
            email="test2@example.com",
            ip_address="127.0.0.1",
        )

        valid = await svc.validate_session(session.id, "wall-2")
        assert valid is not None
        assert valid.id == session.id

    @pytest.mark.asyncio
    async def test_validate_invalid_session(self, db_session):
        svc = SessionService(db_session)
        valid = await svc.validate_session("nonexistent-session", "wall-1")
        assert valid is None

    @pytest.mark.asyncio
    async def test_revoke_session(self, db_session):
        auth_wall = AuthWall(
            id="wall-3",
            name="Test Wall 3",
            auth_type="local",
            session_timeout=3600,
        )
        db_session.add(auth_wall)
        await db_session.commit()

        svc = SessionService(db_session)
        session, _ = await svc.create_session(
            auth_wall_id="wall-3",
            user_type="local",
            user_id="user-3",
            username="revokeuser",
            email="revoke@example.com",
            ip_address="127.0.0.1",
        )

        result = await svc.revoke_session(session.id, "User requested logout")
        assert result is True

        valid = await svc.validate_session(session.id, "wall-3")
        assert valid is None

    @pytest.mark.asyncio
    async def test_get_active_session_count(self, db_session):
        auth_wall = AuthWall(
            id="wall-4",
            name="Test Wall 4",
            auth_type="local",
            session_timeout=3600,
        )
        db_session.add(auth_wall)
        await db_session.commit()

        svc = SessionService(db_session)
        count = await svc.get_active_session_count("wall-4")
        assert count == 0

        await svc.create_session(
            auth_wall_id="wall-4",
            user_type="local",
            user_id="user-4",
            username="counter",
            email="counter@example.com",
            ip_address="127.0.0.1",
        )

        count = await svc.get_active_session_count("wall-4")
        assert count == 1


class TestCookieHelpers:
    """Tests for cookie header helpers."""

    def test_get_cookie_header(self):
        header = get_cookie_header("session-value", 3600)
        assert "session-value" in header
        assert "Max-Age=" in header
        assert "HttpOnly" in header

    def test_get_cookie_header_secure(self):
        header = get_cookie_header("session-value", 3600, secure=True)
        assert "Secure" in header

    def test_get_clear_cookie_header(self):
        header = get_clear_cookie_header()
        assert "Max-Age=0" in header or "expires=" in header.lower()
