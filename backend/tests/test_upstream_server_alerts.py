"""Per-backend-server down/recovered alerts: transitions, flap protection,
grouping with the whole-host alert, maintenance, content and routing."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.alert import AlertChannel, AlertPreference
from app.models.proxy_host import ProxyHost, UpstreamServer, UpstreamServerEvent
from app.models.setting import Setting
from app.schemas.alert import AlertPreferenceCreate
from app.services import health_service
from app.services.alert_service import dispatch_alert, preferences_for, users_opted_out
from app.services.push_service import push_service

T0 = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
WINDOW = timedelta(minutes=5)


def _server(port, status="up", announced="up", **kw):
    values = dict(id=f"srv-{port}", host="10.0.0.5", port=port, enabled=True, down=False, auto_down=False,
                  last_status=status, last_error=None, last_latency_ms=None, alert_status=announced,
                  alert_down_at=None)
    values.update(kw)
    return SimpleNamespace(**values)


def _host(**kw):
    values = dict(id="host-1", domain_names=["app.example.com", "www.app.example.com"], health_status="up",
                  lb_method="least_conn", lb_auto_down=False)
    values.update(kw)
    return SimpleNamespace(**values)


def _plan(host, servers, transition=None, now=T0, previous=None):
    return health_service.plan_server_alerts(host, servers, transition, now, WINDOW, previous=previous)


# ---------------------------------------------------------------------------
# Transition logic
# ---------------------------------------------------------------------------

class TestTransitions:
    def test_up_to_down_sends_once(self):
        a, b = _server(8050, "down"), _server(8051)
        items = _plan(_host(), [a, b], previous={a.id: "up"})
        assert [(i["server"], i["event"], i["alert"]) for i in items] == [(a, "down", "sent")]
        assert a.alert_status == "down" and a.alert_down_at == T0
        # Still down next cycle: nothing new.
        assert _plan(_host(), [a, b], now=T0 + timedelta(minutes=1), previous={a.id: "down"}) == []

    def test_down_to_up_sends_recovered(self):
        a = _server(8050, "up", announced="down", alert_down_at=T0)
        items = _plan(_host(), [a, _server(8051)], now=T0 + timedelta(minutes=3), previous={a.id: "down"})
        assert [(i["event"], i["alert"]) for i in items] == [("recovered", "sent")]
        assert a.alert_status == "up"

    def test_first_failure_is_not_a_transition(self):
        # The two-failure rule keeps last_status "up" after one failed probe,
        # so nothing is planned until it's confirmed.
        a = _server(8050, "up")
        assert _plan(_host(), [a], previous={a.id: "up"}) == []

    def test_never_seen_up_is_not_announced(self):
        a = _server(8050, "down", announced=None)
        assert _plan(_host(), [a, _server(8051)]) == []
        assert a.alert_status is None

    def test_first_sighting_up_is_baseline(self):
        a = _server(8050, "up", announced=None)
        assert _plan(_host(), [a]) == []
        assert a.alert_status == "up"

    def test_unknown_is_ignored(self):
        a = _server(8050, "unknown", announced="up")
        assert _plan(_host(), [a]) == []


# ---------------------------------------------------------------------------
# Flap protection
# ---------------------------------------------------------------------------

class TestFlapProtection:
    def test_second_drop_inside_window_is_held_then_sent_when_window_ends(self):
        a, b = _server(8050, "down"), _server(8051)
        host = _host()
        assert _plan(host, [a, b], now=T0, previous={a.id: "up"})[0]["alert"] == "sent"

        a.last_status = "up"
        assert _plan(host, [a, b], now=T0 + timedelta(minutes=1), previous={a.id: "down"})[0]["alert"] == "sent"

        a.last_status = "down"
        held = _plan(host, [a, b], now=T0 + timedelta(minutes=2), previous={a.id: "up"})
        assert [(i["event"], i["alert"]) for i in held] == [("down", "held")]
        assert a.alert_status == "up"
        # Held quietly while the window runs (no repeated history rows)...
        assert _plan(host, [a, b], now=T0 + timedelta(minutes=4), previous={a.id: "down"}) == []
        # ...and announced once it ends if the server is still down.
        late = _plan(host, [a, b], now=T0 + timedelta(minutes=5, seconds=1), previous={a.id: "down"})
        assert [(i["event"], i["alert"]) for i in late] == [("down", "sent")]
        assert a.alert_status == "down"

    def test_back_up_before_held_alert_sends_nothing(self):
        a = _server(8050, "down", alert_down_at=T0)
        assert _plan(_host(), [a, _server(8051)], now=T0 + timedelta(minutes=2), previous={a.id: "up"})[0]["alert"] == "held"
        a.last_status = "up"
        items = _plan(_host(), [a, _server(8051)], now=T0 + timedelta(minutes=3), previous={a.id: "down"})
        assert [(i["event"], i["alert"]) for i in items] == [("recovered", "held")]

    def test_zero_window_disables_it(self):
        a = _server(8050, "down", alert_down_at=T0)
        items = health_service.plan_server_alerts(_host(), [a], None, T0 + timedelta(seconds=30), timedelta(0))
        assert items[0]["alert"] == "sent"

    async def test_window_from_settings(self, db_session):
        assert await health_service.flap_window(db_session) == timedelta(minutes=5)
        db_session.add(Setting(key="upstream_alert_flap_minutes", value="12"))
        await db_session.commit()
        assert await health_service.flap_window(db_session) == timedelta(minutes=12)

    async def test_bad_window_setting_uses_default(self, db_session):
        db_session.add(Setting(key="upstream_alert_flap_minutes", value="soon"))
        await db_session.commit()
        assert await health_service.flap_window(db_session) == timedelta(minutes=5)


# ---------------------------------------------------------------------------
# Whole-host outage
# ---------------------------------------------------------------------------

class TestAllDown:
    def test_host_down_cycle_groups_server_alerts(self):
        a, b = _server(8050, "down"), _server(8051, "down")
        host = _host(health_status="down")
        items = _plan(host, [a, b], transition="down", previous={a.id: "up", b.id: "up"})
        assert {i["alert"] for i in items} == {"grouped"}
        assert a.alert_status == b.alert_status == "host"
        # Nothing more while the host stays down.
        assert _plan(host, [a, b], previous={a.id: "down", b.id: "down"}) == []

    def test_host_recovery_groups_recoveries_and_reports_servers_still_down(self):
        a = _server(8050, "up", announced="host")
        b = _server(8051, "down", announced="host", last_error="connection refused")
        items = _plan(_host(), [a, b], transition="recovered", previous={a.id: "down", b.id: "down"})
        got = {(i["server"].port, i["event"], i["alert"]) for i in items}
        # a's recovery is covered by the host-recovered alert; b is still down,
        # which the host alert doesn't say, so it gets its own down alert.
        assert got == {(8050, "recovered", "grouped"), (8051, "down", "sent")}

    def test_server_down_while_host_already_down_stays_grouped(self):
        a = _server(8050, "down")
        items = _plan(_host(health_status="down"), [a], previous={a.id: "up"})
        assert [(i["alert"]) for i in items] == ["grouped"]


# ---------------------------------------------------------------------------
# Maintenance and disabled servers
# ---------------------------------------------------------------------------

class TestMaintenance:
    def test_maintenance_server_is_never_announced(self):
        a = _server(8050, "down", down=True)
        assert _plan(_host(), [a, _server(8051)], previous={a.id: "up"}) == []
        assert a.alert_status is None

    def test_ending_maintenance_sends_no_stale_recovery(self):
        a = _server(8050, "down", announced="down", down=True)
        _plan(_host(), [a])
        a.down = False
        a.last_status = "up"
        assert _plan(_host(), [a], previous={a.id: "down"}) == []
        assert a.alert_status == "up"

    def test_disabled_server_skipped(self):
        a = _server(8050, "down", enabled=False)
        assert _plan(_host(), [a], previous={a.id: "up"}) == []


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------

class TestContent:
    def test_down_message(self):
        servers = [_server(8050, "down", last_error="timed out after 5s", auto_down=True),
                   _server(8051), _server(8052), _server(8053, "down"), _server(8054, down=True)]
        host = _host(lb_auto_down=True)
        c = health_service.server_alert_content(host, servers, servers[0], "down", T0)
        assert c["title"] == "Backend Down - app.example.com"
        assert c["message"] == ("10.0.0.5:8050 stopped answering health checks (timed out after 5s). "
                                "2 of 4 backends healthy (1 in maintenance). Taken out of rotation automatically.")
        d = c["data"]
        assert d["domains"] == ["app.example.com", "www.app.example.com"]
        assert d["server"] == "10.0.0.5:8050" and d["server_id"] == "srv-8050"
        assert d["lb_method"] == "least_conn" and d["lb_method_label"] == "Least connections"
        assert d["healthy"] == 2 and d["total"] == 4 and d["auto_down"] is True
        assert d["error"] == "timed out after 5s"

    def test_recovered_message(self):
        servers = [_server(8050, "up", last_latency_ms=12), _server(8051)]
        c = health_service.server_alert_content(_host(), servers, servers[0], "recovered",
                                                T0 + timedelta(minutes=7), down_since=T0)
        assert c["title"] == "Backend Recovered - app.example.com"
        assert c["message"] == "10.0.0.5:8050 is answering again (12 ms, down for 7m). 2 of 2 backends healthy."
        assert c["data"]["downtime"] == "7m" and c["data"]["error"] is None

    def test_ipv6_address_bracketed(self):
        s = _server(8050, "down", host="fd00::5")
        c = health_service.server_alert_content(_host(), [s], s, "down", T0)
        assert c["message"].startswith("[fd00::5]:8050 stopped")
        assert "0 of 1 backend healthy" in c["message"]


# ---------------------------------------------------------------------------
# The health loop end to end (probes mocked)
# ---------------------------------------------------------------------------

async def _make_host(db_session, ports):
    host = ProxyHost(id=str(uuid.uuid4()), domain_names=["lb.example.com"], forward_host="10.0.0.5",
                     forward_port=ports[0], lb_method="round_robin")
    host.upstream_servers = [UpstreamServer(host="10.0.0.5", port=p) for p in ports]
    db_session.add(host)
    await db_session.commit()
    return host.id


class TestHealthLoop:
    @pytest.fixture(autouse=True)
    def _reset(self):
        health_service._server_failures.clear()
        health_service._consecutive_failures.clear()
        health_service._previous_status.clear()

    async def _cycle(self, db_session, up_ports):
        async def fake_probe(scheme, host, port, check_type, path, timeout):
            return (True, None, 5) if port in up_ports else (False, "connection refused", None)

        dispatch = AsyncMock(return_value={"sent": 1, "errors": 0})
        push_all = AsyncMock(return_value={"sent": 0})
        with patch.object(health_service, "probe_server", side_effect=fake_probe), \
             patch.object(push_service, "notify_all", new=push_all), \
             patch.object(push_service, "notify_host_down", new=AsyncMock()), \
             patch.object(push_service, "notify_host_recovered", new=AsyncMock()), \
             patch("app.services.alert_service.dispatch_alert", new=dispatch):
            result = await health_service.run_health_checks(db_session)
        types = [c.kwargs["alert_type"] for c in dispatch.call_args_list]
        return result, types, dispatch, push_all

    async def test_one_down_then_recovered(self, db_session):
        host_id = await _make_host(db_session, [8050, 8051])
        _, types, _, _ = await self._cycle(db_session, {8050, 8051})  # baseline
        assert types == []
        _, types, _, _ = await self._cycle(db_session, {8050})  # first failure
        assert types == []
        result, types, dispatch, push_all = await self._cycle(db_session, {8050})  # confirmed
        assert types == ["upstream_server_down"] and result["servers_down"] == 1
        kwargs = dispatch.call_args.kwargs
        assert kwargs["severity"] == "high" and kwargs["skip_push"] is True
        assert "1 of 2 backends healthy" in kwargs["message"]
        assert kwargs["data"]["server"] == "10.0.0.5:8051"
        assert push_all.call_args.kwargs["notification_type"] == "upstream_server_down"
        _, types, _, _ = await self._cycle(db_session, {8050})  # still down: quiet
        assert types == []
        result, types, dispatch, _ = await self._cycle(db_session, {8050, 8051})
        assert types == ["upstream_server_recovered"] and result["servers_recovered"] == 1

        events = (await db_session.execute(
            select(UpstreamServerEvent).where(UpstreamServerEvent.proxy_host_id == host_id)
            .order_by(UpstreamServerEvent.created_at)
        )).scalars().all()
        assert [(e.event, e.alert, e.server, e.healthy, e.total) for e in events] == [
            ("down", "sent", "10.0.0.5:8051", 1, 2),
            ("recovered", "sent", "10.0.0.5:8051", 2, 2),
        ]

    async def test_all_down_sends_only_the_host_alert(self, db_session):
        await _make_host(db_session, [8050, 8051])
        await self._cycle(db_session, {8050, 8051})
        await self._cycle(db_session, set())
        _, types, _, _ = await self._cycle(db_session, set())
        assert types == ["host_down"]
        _, types, _, _ = await self._cycle(db_session, {8050, 8051})
        assert types == ["host_recovered"]

    async def test_maintenance_server_down_is_silent(self, db_session):
        host_id = await _make_host(db_session, [8050, 8051])
        await self._cycle(db_session, {8050, 8051})
        host = (await db_session.execute(
            select(ProxyHost).options(selectinload(ProxyHost.upstream_servers)).where(ProxyHost.id == host_id)
        )).scalar_one()
        next(s for s in host.upstream_servers if s.port == 8051).down = True
        await db_session.commit()
        for _ in range(3):
            _, types, _, _ = await self._cycle(db_session, {8050})
            assert types == []

    async def test_history_is_capped(self, db_session):
        host_id = await _make_host(db_session, [8050, 8051])
        for i in range(health_service.EVENTS_KEPT_PER_HOST + 5):
            db_session.add(UpstreamServerEvent(proxy_host_id=host_id, server="10.0.0.5:8051", event="down",
                                               alert="sent", created_at=T0 + timedelta(seconds=i)))
        await db_session.commit()
        await health_service._prune_events(db_session, {host_id})
        await db_session.commit()
        rows = (await db_session.execute(
            select(UpstreamServerEvent).where(UpstreamServerEvent.proxy_host_id == host_id)
        )).scalars().all()
        assert len(rows) == health_service.EVENTS_KEPT_PER_HOST
        assert min(r.created_at for r in rows) == T0 + timedelta(seconds=5)


# ---------------------------------------------------------------------------
# Routing: default on, following the host-down preference
# ---------------------------------------------------------------------------

class TestRouting:
    def test_preference_schema_accepts_new_types(self):
        for t in ("upstream_server_down", "upstream_server_recovered", "host_down"):
            assert AlertPreferenceCreate(alert_type=t).alert_type == t
        with pytest.raises(ValidationError):
            AlertPreferenceCreate(alert_type="upstream_server_sideways")

    async def test_inherits_host_down_channels(self, db_session):
        channel = AlertChannel(id="ch-1", user_id="u1", channel_type="webhook", name="hook",
                               config=json.dumps({"url": "https://hooks.example.com/x"}), enabled=True)
        db_session.add_all([
            channel,
            AlertPreference(user_id="u1", alert_type="host_down", min_severity="medium",
                            channels=json.dumps(["ch-1"]), enabled=True),
        ])
        await db_session.commit()
        prefs = await preferences_for(db_session, "upstream_server_down")
        assert [p.alert_type for p in prefs] == ["host_down"]

        with patch("app.services.alert_service._send_to_channel", new=AsyncMock(return_value=True)) as send:
            result = await dispatch_alert(db_session, alert_type="upstream_server_down", severity="high",
                                          title="Backend Down - x", message="m", skip_push=True)
        assert result["sent"] == 1 and send.call_args.args[1].id == "ch-1"

    async def test_own_preference_overrides_and_can_turn_it_off(self, db_session):
        db_session.add_all([
            AlertPreference(user_id="u1", alert_type="host_down", enabled=True),
            AlertPreference(user_id="u1", alert_type="upstream_server_down", enabled=False),
        ])
        await db_session.commit()
        assert await preferences_for(db_session, "upstream_server_down") == []
        assert await users_opted_out(db_session, "upstream_server_down") == {"u1"}
        # The recovered type still follows host_down for this user.
        assert len(await preferences_for(db_session, "upstream_server_recovered")) == 1

    async def test_other_types_do_not_inherit(self, db_session):
        db_session.add(AlertPreference(user_id="u1", alert_type="host_down", enabled=True))
        await db_session.commit()
        assert await preferences_for(db_session, "cert_expiring") == []


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

async def test_events_endpoint(client, auth_headers, db_session):
    host_id = await _make_host(db_session, [8050, 8051])
    db_session.add_all([
        UpstreamServerEvent(proxy_host_id=host_id, server="10.0.0.5:8051", event="down", alert="sent",
                            error="connection refused", healthy=1, total=2, created_at=T0),
        UpstreamServerEvent(proxy_host_id=host_id, server="10.0.0.5:8051", event="recovered", alert="sent",
                            latency_ms=4, healthy=2, total=2, created_at=T0 + timedelta(minutes=3)),
    ])
    await db_session.commit()
    res = await client.get(f"/api/proxy-hosts/{host_id}/upstream-events", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert [e["event"] for e in body] == ["recovered", "down"]
    assert body[1]["error"] == "connection refused" and body[1]["healthy"] == 1

    missing = await client.get(f"/api/proxy-hosts/{uuid.uuid4()}/upstream-events", headers=auth_headers)
    assert missing.status_code == 404
