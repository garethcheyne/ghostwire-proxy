"""System monitoring with Ghostwire Analytics: the settings API, the in-memory getter and the relay."""

from typing import ClassVar

import httpx
import pytest
from app.core.security import decrypt_data
from app.models.setting import Setting
from app.services import ghostwire_analytics
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

URL = "https://analytics.example.com"
SITE = "0b6c3b0e-6a3c-4e0c-9a59-6a8f1f5e2d11"
KEY = "gwe_test_ingest_key_1234567890"

VALID = {
    "enabled": True,
    "url": URL,
    "websiteId": SITE,
    "traceSample": 50,
    "browser": True,
    "replay": False,
    "ingestKey": KEY,
}


@pytest.fixture(autouse=True)
def _monitoring_off():
    """Each test starts (and ends) with monitoring off in memory."""
    ghostwire_analytics._current = None
    yield
    ghostwire_analytics._current = None


async def _stored(db_session, key):
    db_session.expire_all()
    row = (await db_session.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    return row.value if row else None


class TestSettingsApi:
    async def test_defaults_are_off(self, client, admin_user, auth_headers):
        response = await client.get("/api/settings/analytics", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == {
            "enabled": False,
            "url": "",
            "websiteId": "",
            "traceSample": 100,
            "browser": False,
            "replay": False,
            "ingestKeySet": False,
        }

    async def test_admin_only(self, client, regular_user, user_auth_headers):
        assert (await client.get("/api/settings/analytics", headers=user_auth_headers)).status_code == 403
        assert (await client.put("/api/settings/analytics", headers=user_auth_headers, json=VALID)).status_code == 403
        test = await client.post("/api/settings/analytics/test", headers=user_auth_headers, json=VALID)
        assert test.status_code == 403
        assert (await client.get("/api/settings/analytics")).status_code == 401

    async def test_save_encrypts_the_key_and_never_returns_it(self, client, admin_user, auth_headers, db_session):
        response = await client.put("/api/settings/analytics", headers=auth_headers, json=VALID)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ingestKeySet"] is True
        assert body["websiteId"] == SITE
        assert body["traceSample"] == 50
        assert KEY not in response.text

        stored = await _stored(db_session, "analytics_ingest_key")
        assert stored and stored != KEY and KEY not in stored
        assert decrypt_data(stored) == KEY

        again = await client.get("/api/settings/analytics", headers=auth_headers)
        assert again.json()["ingestKeySet"] is True
        assert KEY not in again.text

        # Not through the generic settings list either (masked, and never the plain key).
        listing = await client.get("/api/settings/", headers=auth_headers)
        row = next(s for s in listing.json() if s["key"] == "analytics_ingest_key")
        assert row["value"].startswith("••••")
        assert KEY not in listing.text
        assert stored not in listing.text

    async def test_absent_key_is_kept_and_empty_key_removes_it(self, client, admin_user, auth_headers, db_session):
        await client.put("/api/settings/analytics", headers=auth_headers, json=VALID)
        change = {k: v for k, v in VALID.items() if k != "ingestKey"} | {"traceSample": 10}
        response = await client.put("/api/settings/analytics", headers=auth_headers, json=change)
        assert response.json()["ingestKeySet"] is True
        assert decrypt_data(await _stored(db_session, "analytics_ingest_key")) == KEY

        response = await client.put("/api/settings/analytics", headers=auth_headers, json=VALID | {"ingestKey": ""})
        assert response.status_code == 200
        assert response.json()["ingestKeySet"] is False
        assert not await _stored(db_session, "analytics_ingest_key")

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            ({"url": "http://analytics.example.com"}, "https"),
            ({"url": "ftp://analytics.example.com"}, "valid address"),
            ({"url": "not a url"}, "valid address"),
            ({"websiteId": "not-a-uuid"}, "UUID"),
            ({"ingestKey": "sk_live_123"}, "gwe_"),
            ({"traceSample": 101}, "0 to 100"),
            ({"traceSample": -1}, "0 to 100"),
            ({"url": ""}, "URL"),
            ({"websiteId": ""}, "website ID"),
        ],
    )
    async def test_validation(self, client, admin_user, auth_headers, db_session, change, message):
        response = await client.put("/api/settings/analytics", headers=auth_headers, json=VALID | change)
        assert response.status_code == 422
        assert message in str(response.json()["detail"])
        assert await _stored(db_session, "analytics_enabled") is None  # nothing saved

    async def test_http_allowed_on_localhost_and_empty_values_while_off(self, client, admin_user, auth_headers):
        local = VALID | {"url": "http://localhost:3000/"}
        response = await client.put("/api/settings/analytics", headers=auth_headers, json=local)
        assert response.status_code == 200
        assert response.json()["url"] == "http://localhost:3000"

        off = {"enabled": False, "url": "", "websiteId": "", "traceSample": 100, "browser": False, "replay": False}
        assert (await client.put("/api/settings/analytics", headers=auth_headers, json=off)).status_code == 200

    async def test_generic_settings_routes_refuse_analytics_keys(self, client, admin_user, auth_headers, db_session):
        one = await client.put("/api/settings/analytics_ingest_key", headers=auth_headers, json={"value": KEY})
        assert one.status_code == 422
        bulk = await client.put(
            "/api/settings/", headers=auth_headers, json={"settings": {"analytics_url": "http://evil.example"}}
        )
        assert bulk.status_code == 422
        assert await _stored(db_session, "analytics_ingest_key") is None
        assert await _stored(db_session, "analytics_url") is None

    async def test_replay_needs_visitor_analytics(self, client, admin_user, auth_headers):
        response = await client.put(
            "/api/settings/analytics", headers=auth_headers, json=VALID | {"browser": False, "replay": True}
        )
        assert response.json()["replay"] is False


class _FakeClient:
    calls: ClassVar[list[str]] = []
    status = 200
    error: Exception | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url):
        _FakeClient.calls.append(url)
        if _FakeClient.error:
            raise _FakeClient.error
        return httpx.Response(_FakeClient.status)


class TestConnectionTest:
    @pytest.fixture(autouse=True)
    def _fake_http(self, monkeypatch):
        _FakeClient.calls, _FakeClient.status, _FakeClient.error = [], 200, None
        monkeypatch.setattr(ghostwire_analytics.httpx, "AsyncClient", _FakeClient)

    async def test_answers_and_saves_nothing(self, client, admin_user, auth_headers, db_session):
        response = await client.post("/api/settings/analytics/test", headers=auth_headers, json=VALID)
        assert response.status_code == 200
        assert response.json()["ok"] is True
        assert _FakeClient.calls == [f"{URL}/api/heartbeat"]
        assert await _stored(db_session, "analytics_url") is None

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            ({"url": "http://analytics.example.com"}, "https"),
            ({"websiteId": "nope"}, "UUID"),
            ({"ingestKey": "abc"}, "gwe_"),
        ],
    )
    async def test_same_checks_as_the_registry(self, client, admin_user, auth_headers, change, message):
        response = await client.post("/api/settings/analytics/test", headers=auth_headers, json=VALID | change)
        assert response.json()["ok"] is False
        assert message in response.json()["message"]
        assert _FakeClient.calls == []

    async def test_reports_a_bad_answer_or_no_answer(self, client, admin_user, auth_headers):
        _FakeClient.status = 503
        response = await client.post("/api/settings/analytics/test", headers=auth_headers, json=VALID)
        assert response.json() == {"ok": False, "message": "Analytics answered with HTTP 503."}
        _FakeClient.error = httpx.ConnectError("refused")
        response = await client.post("/api/settings/analytics/test", headers=auth_headers, json=VALID)
        assert response.json()["ok"] is False
        assert "Couldn't reach" in response.json()["message"]


class TestGetConfig:
    async def test_save_refreshes_the_getter(self, client, admin_user, auth_headers):
        assert ghostwire_analytics.get_config() is None
        await client.put("/api/settings/analytics", headers=auth_headers, json=VALID)
        config = ghostwire_analytics.get_config()
        assert config == {
            "url": URL,
            "website_id": SITE,
            "ingest_key": KEY,
            "trace_sample": 50,
            "browser": True,
            "replay": False,
        }
        await client.put("/api/settings/analytics", headers=auth_headers, json=VALID | {"enabled": False})
        assert ghostwire_analytics.get_config() is None

    async def test_refresh_picks_up_a_change_made_elsewhere(self, client, admin_user, auth_headers, db_session):
        await client.put("/api/settings/analytics", headers=auth_headers, json=VALID)
        row = (await db_session.execute(select(Setting).where(Setting.key == "analytics_trace_sample"))).scalar_one()
        row.value = "5"
        await db_session.commit()
        assert ghostwire_analytics.get_config()["trace_sample"] == 50  # memory until the next refresh

        await ghostwire_analytics.refresh(db_session)
        assert ghostwire_analytics.get_config()["trace_sample"] == 5

        flag = (await db_session.execute(select(Setting).where(Setting.key == "analytics_enabled"))).scalar_one()
        flag.value = "false"
        await db_session.commit()
        await ghostwire_analytics.refresh(db_session)
        assert ghostwire_analytics.get_config() is None

    async def test_a_failed_refresh_keeps_the_last_value(self, client, admin_user, auth_headers, monkeypatch):
        await client.put("/api/settings/analytics", headers=auth_headers, json=VALID)

        async def broken(_db):
            raise RuntimeError("database down")

        monkeypatch.setattr(ghostwire_analytics, "load", broken)
        assert (await ghostwire_analytics.refresh(object()))["url"] == URL

    async def test_returns_a_copy(self):
        ghostwire_analytics._set_current(
            {
                "enabled": True,
                "url": URL,
                "website_id": SITE,
                "ingest_key": KEY,
                "trace_sample": 100,
                "browser": False,
                "replay": False,
            }
        )
        ghostwire_analytics.get_config()["url"] = "changed"
        assert ghostwire_analytics.get_config()["url"] == URL

    async def test_internal_endpoint_needs_the_token(self, client, admin_user, auth_headers):
        await client.put("/api/settings/analytics", headers=auth_headers, json=VALID)
        assert (await client.get("/api/internal/analytics-config")).status_code == 401
        response = await client.get(
            "/api/internal/analytics-config", headers={"X-Internal-Auth": "test-internal-token"}
        )
        assert response.status_code == 200
        assert response.json() == {
            "url": URL,
            "websiteId": SITE,
            "ingestKey": KEY,
            "traceSample": 50,
            "browser": True,
            "replay": False,
        }

    async def test_internal_endpoint_null_while_off(self, client):
        response = await client.get(
            "/api/internal/analytics-config", headers={"X-Internal-Auth": "test-internal-token"}
        )
        assert response.status_code == 200
        assert response.json() is None


class TestRelay:
    """POST /internal/otlp/v1/{signal}: the stack's Collector sends here; it forwards with the key."""

    @pytest.fixture
    def upstream(self, monkeypatch):
        calls = []
        real_post = httpx.AsyncClient.post

        async def post(self, url, content=None, headers=None, **kwargs):
            if not str(url).startswith(URL):  # the test's own request to the app
                return await real_post(self, url, content=content, headers=headers, **kwargs)
            calls.append({"url": url, "content": content, "headers": headers})
            return httpx.Response(200, content=b'{"partialSuccess":{}}', headers={"content-type": "application/json"})

        monkeypatch.setattr(httpx.AsyncClient, "post", post)
        return calls

    @staticmethod
    def _on():
        ghostwire_analytics._set_current(
            {
                "enabled": True,
                "url": URL,
                "website_id": SITE,
                "ingest_key": KEY,
                "trace_sample": 100,
                "browser": False,
                "replay": False,
            }
        )

    @staticmethod
    async def _post(peer, path="/internal/otlp/v1/metrics", headers=None, body=b"\x0a\x00"):
        from app.main import app

        transport = ASGITransport(app=app, client=(peer, 40000))
        async with AsyncClient(transport=transport, base_url="http://ghostwire-proxy-api:8000") as ac:
            return await ac.post(
                path, content=body, headers={"content-type": "application/x-protobuf", **(headers or {})}
            )

    async def test_off_is_404(self, upstream):
        response = await self._post("172.20.0.5")
        assert response.status_code == 404
        assert upstream == []

    async def test_on_forwards_with_the_bearer_key(self, upstream):
        self._on()
        response = await self._post("172.20.0.5", path="/internal/otlp/v1/traces")
        assert response.status_code == 200
        assert upstream[0]["url"] == f"{URL}/v1/traces"
        assert upstream[0]["headers"]["authorization"] == f"Bearer {KEY}"
        assert upstream[0]["headers"]["content-type"] == "application/x-protobuf"
        assert upstream[0]["content"] == b"\x0a\x00"

    async def test_private_sources_only(self, upstream):
        self._on()
        assert (await self._post("203.0.113.9")).status_code == 403
        assert (await self._post("172.20.0.5", headers={"x-forwarded-for": "8.8.8.8"})).status_code == 403
        assert (await self._post("172.20.0.5", headers={"x-real-ip": "1.1.1.1"})).status_code == 403
        assert (await self._post("172.20.0.5", headers={"forwarded": "for=9.9.9.9"})).status_code == 403
        assert upstream == []

    async def test_refuses_other_signals_and_types(self, upstream):
        self._on()
        assert (await self._post("10.0.0.2", path="/internal/otlp/v1/logs")).status_code == 404
        assert (await self._post("10.0.0.2", headers={"content-type": "text/plain"})).status_code == 415
        assert upstream == []

    async def test_not_reachable_through_api_prefix(self, client):
        # The admin UI only forwards /api/* to the API; the relay isn't under it.
        self._on()
        response = await client.post(
            "/api/internal/otlp/v1/metrics", content=b"x", headers={"content-type": "application/x-protobuf"}
        )
        assert response.status_code in (401, 404, 405)
