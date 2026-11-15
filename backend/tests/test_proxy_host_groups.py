"""Host groups and ordering on the Hosts page (layout only; never reaches nginx)."""

import uuid

import pytest
from app.models.proxy_host import ProxyHost
from sqlalchemy import select


async def _host(db_session, name: str, **kw) -> ProxyHost:
    host = ProxyHost(
        id=str(uuid.uuid4()),
        domain_names=[f"{name}.example.com"],
        forward_host="127.0.0.1",
        forward_port=8080,
        **kw,
    )
    db_session.add(host)
    await db_session.commit()
    return host


async def _ids_in_order(client, auth_headers) -> list[str]:
    r = await client.get("/api/proxy-hosts/", headers=auth_headers)
    assert r.status_code == 200
    return [(h["group_id"], h["id"]) for h in r.json()]


class TestGroupsCrud:
    async def test_create_list_rename_delete(self, client, auth_headers):
        r = await client.post("/api/proxy-hosts/groups", headers=auth_headers, json={"name": "  Media   apps "})
        assert r.status_code == 201
        media = r.json()
        assert media["name"] == "Media apps"
        assert media["sort_order"] == 0

        r = await client.post("/api/proxy-hosts/groups", headers=auth_headers, json={"name": "Dev"})
        assert r.json()["sort_order"] == 1

        r = await client.get("/api/proxy-hosts/groups", headers=auth_headers)
        assert [g["name"] for g in r.json()] == ["Media apps", "Dev"]

        r = await client.put(f"/api/proxy-hosts/groups/{media['id']}", headers=auth_headers, json={"name": "Media"})
        assert r.status_code == 200 and r.json()["name"] == "Media"

        r = await client.delete(f"/api/proxy-hosts/groups/{media['id']}", headers=auth_headers)
        assert r.status_code == 204
        r = await client.get("/api/proxy-hosts/groups", headers=auth_headers)
        assert [g["name"] for g in r.json()] == ["Dev"]

    async def test_duplicate_name_refused_case_insensitively(self, client, auth_headers):
        await client.post("/api/proxy-hosts/groups", headers=auth_headers, json={"name": "Media"})
        r = await client.post("/api/proxy-hosts/groups", headers=auth_headers, json={"name": "media"})
        assert r.status_code == 409

    async def test_blank_name_refused(self, client, auth_headers):
        r = await client.post("/api/proxy-hosts/groups", headers=auth_headers, json={"name": "   "})
        assert r.status_code == 422

    async def test_regular_user_can_read_but_not_write(self, client, auth_headers, user_auth_headers):
        r = await client.post("/api/proxy-hosts/groups", headers=user_auth_headers, json={"name": "X"})
        assert r.status_code == 403
        r = await client.put("/api/proxy-hosts/groups/layout", headers=user_auth_headers, json={"sections": []})
        assert r.status_code == 403
        r = await client.get("/api/proxy-hosts/groups", headers=user_auth_headers)
        assert r.status_code == 200

    async def test_groups_path_not_taken_for_a_host_id(self, client, auth_headers):
        r = await client.get("/api/proxy-hosts/groups", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestDeleteGroupKeepsHosts:
    async def test_hosts_move_to_end_of_ungrouped_in_order(self, client, auth_headers, db_session):
        group = (await client.post("/api/proxy-hosts/groups", headers=auth_headers, json={"name": "G"})).json()
        loose = await _host(db_session, "loose", sort_order=0)
        a = await _host(db_session, "a", group_id=group["id"], sort_order=0)
        b = await _host(db_session, "b", group_id=group["id"], sort_order=1)

        r = await client.delete(f"/api/proxy-hosts/groups/{group['id']}", headers=auth_headers)
        assert r.status_code == 204

        assert await _ids_in_order(client, auth_headers) == [(None, loose.id), (None, a.id), (None, b.id)]


class TestLayout:
    async def test_save_layout_moves_and_orders(self, client, auth_headers, db_session):
        g1 = (await client.post("/api/proxy-hosts/groups", headers=auth_headers, json={"name": "One"})).json()
        g2 = (await client.post("/api/proxy-hosts/groups", headers=auth_headers, json={"name": "Two"})).json()
        h1 = await _host(db_session, "h1")
        h2 = await _host(db_session, "h2")
        h3 = await _host(db_session, "h3")
        before = (await db_session.get(ProxyHost, h1.id)).updated_at

        r = await client.put(
            "/api/proxy-hosts/groups/layout",
            headers=auth_headers,
            json={
                "sections": [
                    {"group_id": None, "host_ids": [h3.id]},
                    {"group_id": g2["id"], "host_ids": [h2.id, h1.id]},
                    {"group_id": g1["id"], "host_ids": []},
                ]
            },
        )
        assert r.status_code == 204, r.text

        groups = (await client.get("/api/proxy-hosts/groups", headers=auth_headers)).json()
        assert [g["name"] for g in groups] == ["Two", "One"]

        hosts = {h["id"]: h for h in (await client.get("/api/proxy-hosts/", headers=auth_headers)).json()}
        assert (hosts[h3.id]["group_id"], hosts[h3.id]["sort_order"]) == (None, 0)
        assert (hosts[h2.id]["group_id"], hosts[h2.id]["sort_order"]) == (g2["id"], 0)
        assert (hosts[h1.id]["group_id"], hosts[h1.id]["sort_order"]) == (g2["id"], 1)

        # A reorder isn't a config change.
        after = (await db_session.execute(select(ProxyHost.updated_at).where(ProxyHost.id == h1.id))).scalar_one()
        assert after == before

    @pytest.mark.parametrize("problem", ["missing_host", "duplicate_host", "missing_group", "unknown_group"])
    async def test_stale_layout_refused(self, client, auth_headers, db_session, problem):
        g = (await client.post("/api/proxy-hosts/groups", headers=auth_headers, json={"name": "G"})).json()
        h1 = await _host(db_session, "h1")
        h2 = await _host(db_session, "h2")
        sections = {
            "missing_host": [{"group_id": None, "host_ids": [h1.id]}, {"group_id": g["id"], "host_ids": []}],
            "duplicate_host": [
                {"group_id": None, "host_ids": [h1.id, h2.id]},
                {"group_id": g["id"], "host_ids": [h1.id]},
            ],
            "missing_group": [{"group_id": None, "host_ids": [h1.id, h2.id]}],
            "unknown_group": [
                {"group_id": None, "host_ids": [h1.id, h2.id]},
                {"group_id": g["id"], "host_ids": []},
                {"group_id": "nope", "host_ids": []},
            ],
        }[problem]
        r = await client.put("/api/proxy-hosts/groups/layout", headers=auth_headers, json={"sections": sections})
        assert r.status_code == 409


class TestHostGroupField:
    async def test_update_rejects_unknown_group(self, client, auth_headers, db_session):
        h = await _host(db_session, "h")
        r = await client.put(f"/api/proxy-hosts/{h.id}", headers=auth_headers, json={"group_id": "nope"})
        assert r.status_code == 422

    async def test_next_sort_order_helper(self, db_session):
        from app.api.routes.proxy_hosts import _next_sort_order

        assert await _next_sort_order(db_session, None) == 0
        await _host(db_session, "a", sort_order=4)
        assert await _next_sort_order(db_session, None) == 5
