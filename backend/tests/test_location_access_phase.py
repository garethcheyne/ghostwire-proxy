"""Every proxied location gets the host's access phase (auth wall, WAF).

nginx does not carry an access_by_lua handler from `location /` into a sibling
location, so each custom location has to emit it itself. The snapshots under
tests/snapshots/ are complete server blocks; regenerate them with
UPDATE_SNAPSHOTS=1 (or delete the file) after an intended change. CI checks
them with `openresty -t` in the proxy image (job "Generated nginx config").
"""

import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.proxy_host import ProxyHost, ProxyLocation, UpstreamServer
from app.services.openresty_service import generate_server_block

SNAPSHOTS = Path(__file__).parent / "snapshots"


def _defaults(model) -> dict:
    """Column defaults of a model, as a plain dict (scalars only)."""
    values = {}
    for col in model.__table__.columns:
        default = col.default
        if default is not None and not callable(getattr(default, "arg", None)):
            values[col.name] = default.arg
        else:
            values[col.name] = None
    return values


def _host(**overrides):
    values = _defaults(ProxyHost)
    values.update(
        id="11111111-2222-3333-4444-555555555555",
        domain_names=["app.example.test"],
        forward_host="10.0.0.10",
        forward_port=8080,
        access_list=None,
        auth_wall=None,
        upstream_servers=[],
        locations=[],
        certificate=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _location(**overrides):
    values = _defaults(ProxyLocation)
    values.update(
        id="loc-1",
        path="/api",
        forward_host="10.0.0.20",
        forward_port=9000,
        enabled=True,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _location_body(config: str, directive: str) -> str:
    start = config.index(f"location {directive} {{")
    depth = 0
    for i in range(start, len(config)):
        if config[i] == "{":
            depth += 1
        elif config[i] == "}":
            depth -= 1
            if depth == 0:
                return config[start:i + 1]
    raise AssertionError("unterminated location")


WALL = SimpleNamespace(auth_type="multi", name="Staff", theme="default")


class TestCustomLocationAccessPhase:
    def test_walled_host_custom_location_checks_the_wall_and_waf(self):
        host = _host(auth_wall_id="wall-1", auth_wall=WALL, block_exploits=True,
                     locations=[_location()])
        config = generate_server_block(host)
        body = _location_body(config, "/api")
        assert "require('auth_wall').access()" in body
        assert "require('waf').access()" in body
        assert body.index("access_by_lua_block") < body.index("proxy_pass")

    def test_custom_location_matches_the_default_location(self):
        for wall, waf in [(True, True), (True, False), (False, True)]:
            host = _host(auth_wall_id="wall-1" if wall else None,
                         auth_wall=WALL if wall else None,
                         block_exploits=waf,
                         locations=[_location(), _location(id="loc-2", path="\\.php$", match_type="regex")])
            config = generate_server_block(host)
            root = _location_body(config, "/")
            root_phase = re.search(r"access_by_lua_block \{.*?\}\n", root, re.S).group(0)
            for directive in ("/api", "~ \\.php$"):
                body = _location_body(config, directive)
                assert root_phase in body, (wall, waf, directive)

    def test_waf_only_host(self):
        host = _host(block_exploits=True, locations=[_location()])
        body = _location_body(generate_server_block(host), "/api")
        assert "require('waf').access()" in body
        assert "auth_wall" not in body

    def test_no_wall_no_waf_emits_no_access_phase(self):
        host = _host(block_exploits=False, locations=[_location()])
        config = generate_server_block(host)
        assert "access_by_lua" not in config

    def test_auth_portal_locations_stay_open(self):
        host = _host(auth_wall_id="wall-1", auth_wall=WALL, block_exploits=True,
                     locations=[_location()])
        config = generate_server_block(host)
        for directive in ("/__auth/", "/api/auth-portal/", "/.well-known/acme-challenge/"):
            assert "access_by_lua" not in _location_body(config, directive), directive

    def test_disabled_location_is_not_written(self):
        host = _host(auth_wall_id="wall-1", auth_wall=WALL,
                     locations=[_location(enabled=False)])
        assert "location /api {" not in generate_server_block(host)


def _snapshot_hosts():
    walled = _host(
        auth_wall_id="wall-1",
        auth_wall=WALL,
        block_exploits=True,
        rate_limit_enabled=True,
        traffic_logging_enabled=True,
        locations=[
            _location(rate_limit_enabled=True, rate_limit_burst=10),
            _location(id="loc-2", path="/ws", forward_port=9001, websockets_support=True, priority=5),
            _location(id="loc-3", path="\\.(png|jpg)$", match_type="regex_case_insensitive",
                      cache_enabled=True, cache_valid="200 10m"),
        ],
    )
    balanced = _host(
        id="66666666-7777-8888-9999-000000000000",
        domain_names=["lb.example.test"],
        auth_wall_id="wall-2",
        auth_wall=WALL,
        block_exploits=False,
        lb_method="least_conn",
        upstream_servers=[
            SimpleNamespace(**{**_defaults(UpstreamServer), "id": f"s{i}", "host": f"10.0.1.{i}",
                               "port": 8080, "enabled": True, "backup": i == 4})
            for i in range(1, 5)
        ],
        locations=[_location(path="/admin")],
    )
    return {"walled_custom_locations": walled, "balanced_walled": balanced}


@pytest.mark.parametrize("name", sorted(_snapshot_hosts()))
def test_server_block_snapshot(name):
    config = generate_server_block(_snapshot_hosts()[name])
    path = SNAPSHOTS / f"{name}.conf"
    if os.environ.get("UPDATE_SNAPSHOTS") == "1" or not path.exists():
        SNAPSHOTS.mkdir(exist_ok=True)
        path.write_text(config, encoding="utf-8", newline="\n")
    assert config == path.read_text(encoding="utf-8")
