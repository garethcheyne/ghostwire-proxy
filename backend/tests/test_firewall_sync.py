"""Firewall Sync pushes already-blocked IPs, unblock takes them off, LAN addresses are never pushed."""

import pytest
from app.api.routes import firewalls as firewall_routes
from app.models.firewall import FirewallBlocklist, FirewallConnector
from app.models.waf import ThreatActor
from app.services import firewall_service
from app.services.firewall_service import is_bannable
from sqlalchemy import select


class FakeFirewall:
    def __init__(self):
        self.ips: set[str] = set()

    async def add_to_blocklist(self, ip, comment=""):
        self.ips.add(ip)
        return True, "ok"

    async def remove_from_blocklist(self, ip):
        self.ips.discard(ip)
        return True


@pytest.fixture
async def firewall(db_session, monkeypatch):
    fake = FakeFirewall()
    monkeypatch.setattr(firewall_routes, "get_firewall_connector", lambda c: fake)
    monkeypatch.setattr(firewall_service, "get_connector", lambda c: fake)
    connector = FirewallConnector(name="GW", connector_type="unifi", host="192.0.2.10", enabled=True)
    db_session.add(connector)
    await db_session.commit()
    return connector, fake


def test_is_bannable():
    assert is_bannable("34.80.134.110")
    assert is_bannable("2a00:1450:4009:81f::200e")
    for ip in ("192.168.0.1", "10.1.2.3", "172.20.0.5", "127.0.0.1", "::1", "fe80::1", "not-an-ip"):
        assert not is_bannable(ip), ip


@pytest.mark.asyncio
async def test_sync_pushes_already_blocked_actors(client, auth_headers, db_session, firewall):
    connector, fake = firewall
    db_session.add_all(
        [
            ThreatActor(ip_address="34.80.134.110", current_status="perm_blocked"),
            ThreatActor(ip_address="35.198.50.207", current_status="firewall_banned"),
            ThreatActor(ip_address="198.51.100.200", current_status="monitored"),
            # The gateway, seen as the source of all NAT-loopback LAN traffic.
            ThreatActor(ip_address="192.168.0.1", current_status="perm_blocked"),
        ]
    )
    await db_session.commit()

    r = await client.post(f"/api/firewalls/{connector.id}/sync", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert fake.ips == {"34.80.134.110", "35.198.50.207"}
    assert (body["pushed"], body["skipped"], body["errors"]) == (2, 1, 0)

    # A second sync has nothing new to push.
    r = await client.post(f"/api/firewalls/{connector.id}/sync", headers=auth_headers)
    assert r.json()["pushed"] == 0


@pytest.mark.asyncio
async def test_unblock_removes_from_firewall(client, auth_headers, db_session, firewall):
    connector, fake = firewall
    db_session.add(ThreatActor(ip_address="34.80.134.110", current_status="perm_blocked"))
    await db_session.commit()
    await client.post(f"/api/firewalls/{connector.id}/sync", headers=auth_headers)
    assert "34.80.134.110" in fake.ips

    r = await client.post("/api/waf/actors/34.80.134.110/unblock", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["firewalls_removed"] == 1
    assert fake.ips == set()
    db_session.expire_all()
    statuses = (await db_session.execute(select(FirewallBlocklist.status))).scalars().all()
    assert statuses == ["removed"]


@pytest.mark.asyncio
async def test_firewall_ban_refuses_private_addresses(client, auth_headers, firewall):
    _, fake = firewall
    r = await client.post("/api/waf/actors/192.168.0.1/firewall-ban", headers=auth_headers)
    assert r.status_code == 400
    r = await client.post(
        "/api/waf/actors/bulk-firewall-ban", headers=auth_headers, json={"ips": ["34.80.134.110", "10.0.0.1"]}
    )
    assert r.status_code == 400
    assert fake.ips == set()
