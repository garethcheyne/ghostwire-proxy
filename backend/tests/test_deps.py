"""Tests for deps module — authentication dependencies."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.security import create_access_token, create_refresh_token
from app.api.deps import get_current_user, get_current_admin_user
from app.models.user import User
from fastapi import HTTPException


class TestGetCurrentUser:
    """Tests for the get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self, db_session, admin_user):
        token = create_access_token(data={"sub": admin_user.id})
        credentials = MagicMock()
        credentials.credentials = token

        user = await get_current_user(credentials=credentials, db=db_session)
        assert user.id == admin_user.id
        assert user.email == "admin@test.com"

    @pytest.mark.asyncio
    async def test_invalid_token_raises(self, db_session):
        credentials = MagicMock()
        credentials.credentials = "invalid-token"

        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials, db=db_session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_token_rejected(self, db_session, admin_user):
        token = create_refresh_token(data={"sub": admin_user.id})
        credentials = MagicMock()
        credentials.credentials = token

        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials, db=db_session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_deleted_user_raises(self, db_session):
        token = create_access_token(data={"sub": "deleted-user-id"})
        credentials = MagicMock()
        credentials.credentials = token

        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials, db=db_session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_user_raises(self, db_session, inactive_user):
        token = create_access_token(data={"sub": inactive_user.id})
        credentials = MagicMock()
        credentials.credentials = token

        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials, db=db_session)
        assert exc.value.status_code == 403


class TestGetCurrentAdminUser:
    """Tests for the get_current_admin_user dependency."""

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
