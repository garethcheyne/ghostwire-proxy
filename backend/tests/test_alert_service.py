"""Tests for alert service — dispatch, channel routing, and sending."""

import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.alert_service import (
    dispatch_alert,
    _send_to_channel,
    _send_webhook,
    _send_slack,
    _send_telegram,
    _send_email,
)
from app.models.alert import AlertChannel, AlertPreference, PushSubscription


class TestDispatchAlert:
    """Tests for the main dispatch_alert function."""

    @pytest.mark.asyncio
    async def test_dispatch_with_no_preferences(self, db_session):
        result = await dispatch_alert(
            db_session, alert_type="security", severity="high",
            title="Test Alert", message="Something happened",
        )
        assert result["sent"] == 0
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_dispatch_skips_low_severity(self, db_session):
        pref = AlertPreference(
            id="pref-1",
            user_id="user-1",
            alert_type="security",
            min_severity="high",
            enabled=True,
        )
        db_session.add(pref)
        await db_session.commit()

        result = await dispatch_alert(
            db_session, alert_type="security", severity="low",
            title="Low Alert", message="Not important",
        )
        assert result["sent"] == 0

    @pytest.mark.asyncio
    async def test_dispatch_disabled_preference_skipped(self, db_session):
        pref = AlertPreference(
            id="pref-2",
            user_id="user-1",
            alert_type="security",
            min_severity="low",
            enabled=False,
        )
        db_session.add(pref)
        await db_session.commit()

        result = await dispatch_alert(
            db_session, alert_type="security", severity="critical",
            title="Critical", message="Important",
        )
        assert result["sent"] == 0


class TestSendToChannel:
    """Tests for channel-specific dispatch."""

    @pytest.mark.asyncio
    async def test_send_to_webhook_channel(self, db_session):
        channel = MagicMock(spec=AlertChannel)
        channel.channel_type = "webhook"
        channel.config = json.dumps({"url": "https://example.com/webhook"})

        with patch("app.services.alert_service._send_webhook", return_value=True) as mock_webhook:
            result = await _send_to_channel(db_session, channel, "Title", "Message")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_to_email_channel(self, db_session):
        channel = MagicMock(spec=AlertChannel)
        channel.channel_type = "email"
        channel.config = json.dumps({})

        result = await _send_to_channel(db_session, channel, "Title", "Message")
        assert result is True  # Email is a placeholder that always returns True

    @pytest.mark.asyncio
    async def test_send_to_unknown_channel(self, db_session):
        channel = MagicMock(spec=AlertChannel)
        channel.channel_type = "unknown"

        result = await _send_to_channel(db_session, channel, "Title", "Message")
        assert result is False


class TestSendWebhook:
    """Tests for webhook sending."""

    @pytest.mark.asyncio
    async def test_webhook_success(self):
        channel = MagicMock(spec=AlertChannel)
        channel.config = json.dumps({"url": "https://example.com/hook"})

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                post=AsyncMock(return_value=mock_resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _send_webhook(channel, "Title", "Message")

        assert result is True

    @pytest.mark.asyncio
    async def test_webhook_no_url(self):
        channel = MagicMock(spec=AlertChannel)
        channel.config = json.dumps({})

        result = await _send_webhook(channel, "Title", "Message")
        assert result is False

    @pytest.mark.asyncio
    async def test_webhook_exception(self):
        channel = MagicMock(spec=AlertChannel)
        channel.config = json.dumps({"url": "https://example.com/hook"})

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                post=AsyncMock(side_effect=Exception("Connection refused"))
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _send_webhook(channel, "Title", "Message")

        assert result is False


class TestSendSlack:
    """Tests for Slack sending."""

    @pytest.mark.asyncio
    async def test_slack_no_webhook_url(self):
        channel = MagicMock(spec=AlertChannel)
        channel.config = json.dumps({})

        result = await _send_slack(channel, "Title", "Message")
        assert result is False

    @pytest.mark.asyncio
    async def test_slack_success(self):
        channel = MagicMock(spec=AlertChannel)
        channel.config = json.dumps({"webhook_url": "https://hooks.slack.com/test"})

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                post=AsyncMock(return_value=mock_resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _send_slack(channel, "Title", "Message")

        assert result is True


class TestSendTelegram:
    """Tests for Telegram sending."""

    @pytest.mark.asyncio
    async def test_telegram_no_token(self):
        channel = MagicMock(spec=AlertChannel)
        channel.config = json.dumps({})

        result = await _send_telegram(channel, "Title", "Message")
        assert result is False

    @pytest.mark.asyncio
    async def test_telegram_no_chat_id(self):
        channel = MagicMock(spec=AlertChannel)
        channel.config = json.dumps({"bot_token": "123:ABC"})

        result = await _send_telegram(channel, "Title", "Message")
        assert result is False

    @pytest.mark.asyncio
    async def test_telegram_success(self):
        channel = MagicMock(spec=AlertChannel)
        channel.config = json.dumps({"bot_token": "123:ABC", "chat_id": "456"})

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock(
                post=AsyncMock(return_value=mock_resp)
            ))
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await _send_telegram(channel, "Title", "Message")

        assert result is True


class TestSendEmail:
    """Tests for email sending (placeholder)."""

    @pytest.mark.asyncio
    async def test_email_always_returns_true(self):
        channel = MagicMock(spec=AlertChannel)
        channel.config = json.dumps({})
        result = await _send_email(channel, "Title", "Message")
        assert result is True
