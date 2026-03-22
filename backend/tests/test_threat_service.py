"""Tests for threat service — recording events, evaluating thresholds, blocking."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone

from app.services.threat_service import (
    record_threat_event,
    check_ip_blocked,
)
from app.models.waf import ThreatEvent, ThreatActor


class TestRecordThreatEvent:
    """Tests for recording threat events."""

    @pytest.mark.asyncio
    async def test_record_new_event(self, db_session):
        event = await record_threat_event(
            db=db_session,
            client_ip="192.0.2.1",
            category="xss",
            severity="high",
            action_taken="blocked",
            matched_payload="<script>alert(1)</script>",
        )
        assert event is not None
        assert event.client_ip == "192.0.2.1"
        assert event.category == "xss"
        assert event.severity == "high"

    @pytest.mark.asyncio
    async def test_record_event_creates_actor(self, db_session):
        from sqlalchemy import select

        await record_threat_event(
            db=db_session,
            client_ip="10.0.0.1",
            category="sqli",
            severity="critical",
            action_taken="blocked",
        )

        result = await db_session.execute(
            select(ThreatActor).where(ThreatActor.ip_address == "10.0.0.1")
        )
        actor = result.scalar_one_or_none()
        assert actor is not None
        assert actor.ip_address == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_record_event_increments_actor_score(self, db_session):
        from sqlalchemy import select

        await record_threat_event(
            db=db_session,
            client_ip="10.0.0.2",
            category="brute_force",
            severity="medium",
            action_taken="logged",
        )
        await record_threat_event(
            db=db_session,
            client_ip="10.0.0.2",
            category="brute_force",
            severity="medium",
            action_taken="logged",
        )

        result = await db_session.execute(
            select(ThreatActor).where(ThreatActor.ip_address == "10.0.0.2")
        )
        actor = result.scalar_one_or_none()
        assert actor is not None
        assert actor.total_events >= 2


class TestCheckIpBlocked:
    """Tests for checking if an IP is blocked."""

    @pytest.mark.asyncio
    async def test_unblocked_ip(self, db_session):
        blocked, reason = await check_ip_blocked(db_session, "192.0.2.100")
        assert blocked is False

    @pytest.mark.asyncio
    async def test_blocked_ip(self, db_session):
        actor = ThreatActor(
            id="actor-1",
            ip_address="192.0.2.200",
            current_status="perm_blocked",
            threat_score=100,
            total_events=10,
        )
        db_session.add(actor)
        await db_session.commit()

        blocked, reason = await check_ip_blocked(db_session, "192.0.2.200")
        assert blocked is True

    @pytest.mark.asyncio
    async def test_monitored_ip_not_blocked(self, db_session):
        actor = ThreatActor(
            id="actor-2",
            ip_address="192.0.2.201",
            current_status="monitored",
            threat_score=30,
            total_events=5,
        )
        db_session.add(actor)
        await db_session.commit()

        blocked, reason = await check_ip_blocked(db_session, "192.0.2.201")
        assert blocked is False
