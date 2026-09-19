"""AbuseIPDB call discipline.

The failure these guard against is quiet and expensive: 641 lookups in one day
came back HTTP 429, so IP intelligence silently stopped populating. The cause
was not one bug but three compounding ones — a refresh wiped the stored score,
the blank score then looked like a cache miss, and a 429 was indistinguishable
from a real answer of "nothing known".
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select

from app.models.honeypot import IpEnrichment
from app.services import enrichment_service as es


@pytest.fixture(autouse=True)
def _clear_cooldown():
    """The rate-limit cooldown is module-level; don't leak it between tests."""
    es._ABUSE_RATE_LIMITED_UNTIL = None
    yield
    es._ABUSE_RATE_LIMITED_UNTIL = None


def _fake_sources(calls, score=42):
    async def abuse(ip, key):
        calls.append(ip)
        return {"abuseConfidenceScore": score, "totalReports": 7}, True

    async def ipapi(ip):
        return {"countryCode": "NZ", "country": "New Zealand"}

    async def rdns(ip):
        return None

    return abuse, ipapi, rdns


class TestNeverQueriesAnIpTwice:
    @pytest.mark.asyncio
    async def test_second_lookup_uses_the_stored_answer(self, db_session):
        calls = []
        abuse, ipapi, rdns = _fake_sources(calls)
        with patch.object(es, "_lookup_abuseipdb", abuse), \
             patch.object(es, "_lookup_ip_api", ipapi), \
             patch.object(es, "_reverse_dns", rdns):
            await es.enrich_ip(db_session, "203.0.113.1", abuseipdb_key="k")
            await es.enrich_ip(db_session, "203.0.113.1", abuseipdb_key="k")

        assert calls == ["203.0.113.1"]

    @pytest.mark.asyncio
    async def test_forced_refresh_still_does_not_re_query(self, db_session):
        calls = []
        abuse, ipapi, rdns = _fake_sources(calls)
        with patch.object(es, "_lookup_abuseipdb", abuse), \
             patch.object(es, "_lookup_ip_api", ipapi), \
             patch.object(es, "_reverse_dns", rdns):
            await es.enrich_ip(db_session, "203.0.113.2", abuseipdb_key="k")
            # force=True refreshes geo/rDNS, which are free — it must not buy
            # another metered reputation call.
            await es.enrich_ip(db_session, "203.0.113.2", force=True, abuseipdb_key="k")

        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_stale_cache_refresh_preserves_the_score(self, db_session):
        """A refresh past the TTL previously overwrote abuse_score with None,
        which made the row look unchecked and bought another call."""
        calls = []
        abuse, ipapi, rdns = _fake_sources(calls, score=88)
        with patch.object(es, "_lookup_abuseipdb", abuse), \
             patch.object(es, "_lookup_ip_api", ipapi), \
             patch.object(es, "_reverse_dns", rdns):
            await es.enrich_ip(db_session, "203.0.113.3", abuseipdb_key="k")

            row = (await db_session.execute(
                select(IpEnrichment).where(IpEnrichment.ip_address == "203.0.113.3")
            )).scalar_one()
            old = datetime.now(timezone.utc) - timedelta(days=30)
            row.updated_at = old
            row.enriched_at = old
            await db_session.commit()

            await es.enrich_ip(db_session, "203.0.113.3", abuseipdb_key="k")

        row = (await db_session.execute(
            select(IpEnrichment).where(IpEnrichment.ip_address == "203.0.113.3")
        )).scalar_one()
        assert len(calls) == 1
        assert row.abuse_score == 88
        assert row.abuse_checked_at is not None

    @pytest.mark.asyncio
    async def test_a_different_ip_is_still_looked_up(self, db_session):
        calls = []
        abuse, ipapi, rdns = _fake_sources(calls)
        with patch.object(es, "_lookup_abuseipdb", abuse), \
             patch.object(es, "_lookup_ip_api", ipapi), \
             patch.object(es, "_reverse_dns", rdns):
            await es.enrich_ip(db_session, "203.0.113.4", abuseipdb_key="k")
            await es.enrich_ip(db_session, "203.0.113.5", abuseipdb_key="k")

        assert calls == ["203.0.113.4", "203.0.113.5"]

    @pytest.mark.asyncio
    async def test_no_key_means_no_call(self, db_session):
        calls = []
        abuse, ipapi, rdns = _fake_sources(calls)
        with patch.object(es, "_lookup_abuseipdb", abuse), \
             patch.object(es, "_lookup_ip_api", ipapi), \
             patch.object(es, "_reverse_dns", rdns):
            await es.enrich_ip(db_session, "203.0.113.6", abuseipdb_key=None)

        assert calls == []


class TestRateLimitCooldown:
    @pytest.mark.asyncio
    async def test_429_reports_failure_not_an_empty_answer(self):
        """A 429 must not be recorded as 'AbuseIPDB knows nothing about this
        IP' — that is what made a rate-limited day poison the cache."""
        class Resp:
            status_code = 429
            def json(self): return {}

        class Client:
            calls = 0
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, *a, **k):
                Client.calls += 1
                return Resp()

        with patch.object(httpx, "AsyncClient", lambda **k: Client()):
            data, answered = await es._lookup_abuseipdb("1.2.3.4", "k")
            assert answered is False
            assert data == {}
            assert es._abuse_is_rate_limited() is True

            # Every subsequent IP is skipped without another HTTP request.
            await es._lookup_abuseipdb("5.6.7.8", "k")
            assert Client.calls == 1

    @pytest.mark.asyncio
    async def test_cooldown_expires(self):
        es._ABUSE_RATE_LIMITED_UNTIL = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert es._abuse_is_rate_limited() is False
