"""Concurrent threat events for one previously-unseen IP.

Observed in production: POST /api/internal/threats/log returned 500 with
`UniqueViolationError on ix_threat_actors_ip_address`, roughly 1 call in 12.
The endpoint SELECTed the actor, found nothing, and INSERTed — so two events
arriving together both inserted and one lost. The request the WAF had blocked
was then never recorded, which is the part that matters: security logging
dropping records silently.

An attacker firing several probes at once is precisely the traffic that
produces this, so it fails exactly when it is least affordable.
"""
import asyncio
import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.waf import ThreatActor, ThreatEvent
from app.services.threat_service import record_threat_event

IP = "198.51.100.200"


@pytest.fixture
async def sessions():
    """A sessionmaker owned by this test.

    Each simulated request needs its own session — sharing one would serialise
    the writes and hide the very race under test. The app-wide AsyncSessionLocal
    cannot be used for that here: its pool outlives a single test's event loop,
    so asyncpg tries to cancel a command on a closed loop during teardown.
    NullPool plus an explicit dispose keeps every connection inside this test.
    """
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield maker
    finally:
        await engine.dispose()


async def _log_one(maker, ip: str, severity: str = "high"):
    async with maker() as db:
        return await record_threat_event(
            db=db,
            client_ip=ip,
            category="sqli",
            severity=severity,
            action_taken="blocked",
            request_method="GET",
            request_uri="/",
            host="example.test",
        )


class TestConcurrentThreatEvents:
    @pytest.mark.asyncio
    async def test_simultaneous_events_for_a_new_ip_all_succeed(self, db_session, sessions):
        results = await asyncio.gather(
            *[_log_one(sessions, IP) for _ in range(12)], return_exceptions=True
        )
        errors = [r for r in results if isinstance(r, Exception)]
        assert not errors, f"{len(errors)} failed, first: {errors[0]!r}"

    @pytest.mark.asyncio
    async def test_exactly_one_actor_row_and_no_lost_events(self, db_session, sessions):
        ip = "198.51.100.201"
        await asyncio.gather(*[_log_one(sessions, ip) for _ in range(10)])

        async with sessions() as db:
            actors = (await db.execute(
                select(func.count()).select_from(ThreatActor).where(ThreatActor.ip_address == ip)
            )).scalar()
            events = (await db.execute(
                select(func.count()).select_from(ThreatEvent).where(ThreatEvent.client_ip == ip)
            )).scalar()
            actor = (await db.execute(
                select(ThreatActor).where(ThreatActor.ip_address == ip)
            )).scalar_one()

        assert actors == 1
        assert events == 10, "a blocked request went unrecorded"
        # Counters come from the stored column, so concurrent increments
        # accumulate instead of overwriting one another.
        assert actor.total_events == 10

    @pytest.mark.asyncio
    async def test_country_is_filled_but_never_overwritten(self, db_session, sessions):
        ip = "198.51.100.202"
        await _log_one(sessions, ip)
        async with sessions() as db:
            actor = (await db.execute(
                select(ThreatActor).where(ThreatActor.ip_address == ip)
            )).scalar_one()
            actor.country_code = "NZ"
            actor.country_name = "New Zealand"
            await db.commit()

        await _log_one(sessions, ip)

        async with sessions() as db:
            actor = (await db.execute(
                select(ThreatActor).where(ThreatActor.ip_address == ip)
            )).scalar_one()
        assert actor.country_code == "NZ"
