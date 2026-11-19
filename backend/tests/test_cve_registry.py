"""The CVE registry (cve/) and its engine (scripts/ghostwire_cve.py).

Every advisory in cve/ is validated here, so CI refuses a malformed one; the rest pins the engine's
version, exposure and plan rules, and checks the advisories against config this API really generates.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.models.proxy_host import ProxyHost
from app.services import openresty_service
from app.services.openresty_service import generate_server_block

ROOT = Path(__file__).resolve().parents[2]
CVE_DIR = ROOT / "cve"

_spec = importlib.util.spec_from_file_location("ghostwire_cve", ROOT / "scripts" / "ghostwire_cve.py")
cve = importlib.util.module_from_spec(_spec)
sys.modules["ghostwire_cve"] = cve  # dataclasses look their module up by name
_spec.loader.exec_module(cve)


def manifest(**overrides) -> dict:
    data = {
        "schema": 1,
        "id": "CVE-2099-0001",
        "title": "Test flaw",
        "severity": "high",
        "published": "2099-01-01",
        "summary": "A test advisory.",
        "affects": {"component": "nginx", "introduced": "1.9.5", "fixed": ["1.30.7", "1.31.9"]},
        "exposure": [{"id": "http2", "text": "cfg", "pattern": r"^\s*http2\s+on\s*;", "describe": "HTTP/2 on"}],
        "mitigations": [{"name": "disable_http2", "removes": ["http2"], "describe": "turn HTTP/2 off"}],
    }
    data.update(overrides)
    return data


def advisory(**overrides):
    adv, errors = cve.validate_manifest(manifest(**overrides), overrides.get("id", "CVE-2099-0001"))
    assert errors == []
    return adv


def facts(version="1.25.3", cfg="http2 on;", active=frozenset(), target=None):
    return cve.Facts(
        versions={"nginx": version} if version else {},
        target_versions={"nginx": target} if target else {},
        texts={"cfg": cfg} if cfg is not None else {},
        active=set(active) if active is not None else None,
        supported={"disable_http2"},
    )


# ── The registry itself ─────────────────────────────────────────────────────────────────────────


def test_every_recorded_advisory_is_valid():
    advisories, invalid = cve.load_dir(CVE_DIR)
    assert invalid == {}, json.dumps(invalid, indent=2)
    assert {a.id for a in advisories} >= {"CVE-2026-123007", "CVE-2026-123633"}


def test_recorded_mitigations_are_ones_the_api_implements():
    from app.services.cve_mitigation_service import MITIGATIONS

    advisories, _ = cve.load_dir(CVE_DIR)
    named = {m["name"] for a in advisories for m in a.mitigations}
    assert named <= MITIGATIONS.keys()


def test_upgrade_script_lists_the_api_mitigations():
    from app.services.cve_mitigation_service import MITIGATIONS

    script = (ROOT / "upgradeGhostwireProxy.sh").read_text()
    for name in MITIGATIONS:
        assert name in script.split("CVE_MITIGATIONS=", 1)[1].split("\n", 1)[0]


# ── Versions ────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("version", "affected"),
    [
        ("1.9.4", False),  # before introduced
        ("1.9.5", True),
        ("1.25.3", True),  # an older branch with no fix of its own
        ("1.28.2", True),
        ("1.30.6", True),
        ("1.30.7", False),  # its branch's fix
        ("1.30.9", False),
        ("1.31.8", True),
        ("1.31.9", False),
        ("1.32.0", False),  # newer than every fix
        ("2.0", False),
    ],
)
def test_affected_range(version, affected):
    adv = advisory()
    assert cve.in_range(cve.parse_version(version), adv.introduced, adv.fixed) is affected


def test_no_fix_yet_means_every_version_from_introduced():
    adv = advisory(affects={"component": "nginx", "introduced": None, "fixed": []})
    assert cve.in_range(cve.parse_version("99.0"), adv.introduced, adv.fixed)


@pytest.mark.parametrize("text", ["", "1.25.3-alpine", "latest", None])
def test_unreadable_versions(text):
    assert cve.parse_version(text) is None


# ── Statuses ────────────────────────────────────────────────────────────────────────────────────


def status(f, **overrides):
    return cve.evaluate([advisory(**overrides)], f)[0].status


def test_statuses():
    assert status(facts()) == cve.VULNERABLE
    assert status(facts(version="1.31.9")) == cve.FIXED
    assert status(facts(cfg="# http2 on; in a comment")) == cve.NOT_EXPOSED
    assert status(facts(cfg="", active={"disable_http2"})) == cve.MITIGATED


def test_missing_facts_are_unknown_never_safe():
    assert status(facts(version=None)) == cve.UNKNOWN
    assert status(facts(cfg=None)) == cve.UNKNOWN


def test_one_false_condition_outweighs_an_unknown_one():
    cond = {"id": "mail", "text": "other", "pattern": "mail", "describe": "mail"}
    exposure = [*manifest()["exposure"], cond]
    assert status(facts(cfg=""), exposure=exposure) == cve.NOT_EXPOSED


def test_no_exposure_conditions_means_the_version_alone_exposes():
    assert status(facts(cfg=None), exposure=[], mitigations=[]) == cve.VULNERABLE


def test_old_listen_http2_syntax_counts():
    assert status(facts(cfg="listen 443 ssl http2;"), exposure=cve_exposure("CVE-2026-123007")) == cve.VULNERABLE


def recorded_pattern(cve_id: str, condition: str) -> str:
    data = json.loads((CVE_DIR / f"{cve_id}.json").read_text())
    return next(c["pattern"] for c in data["exposure"] if c["id"] == condition)


@pytest.mark.parametrize(
    ("cve_id", "condition", "line", "matches"),
    [
        # Custom snippets put directives anywhere on a line; a commented-out one doesn't count.
        ("CVE-2026-123633", "proxy_pass", "    location / { proxy_pass http://x; }", True),
        ("CVE-2026-123633", "proxy_pass", "    proxy_pass http://x;", True),
        ("CVE-2026-123633", "proxy_pass", "    # proxy_pass http://x;", False),
        ("CVE-2026-123633", "proxy_pass", "    proxy_pass_header Set-Cookie;", False),
        ("CVE-2026-123633", "proxy_pass", "    set $my_proxy_pass 1;", False),
        ("CVE-2026-123007", "http2", "server { listen 443 ssl; http2 on; }", True),
        ("CVE-2026-123007", "http2", "    listen 443 ssl http2;", True),
        ("CVE-2026-123007", "http2", "    listen 443 ssl; # http2", False),
        # What openresty_service writes when the mitigation is on must not read as HTTP/2.
        (
            "CVE-2026-123007",
            "http2",
            "    # HTTP/2 is off for this host: CVE mitigation disable_http2 (cve/README.md)",
            False,
        ),
        ("CVE-2026-121810", "http3", "    listen 443 quic reuseport;", True),
        ("CVE-2026-123634", "resolver", "    resolver 127.0.0.11 valid=300s;", True),
        ("CVE-2026-123634", "resolver", "    resolver_timeout 5s;", False),
        ("CVE-2026-123634", "variable_proxy_pass", "        proxy_pass http://$auth_portal_api;", True),
        ("CVE-2026-123634", "variable_proxy_pass", "        proxy_pass http://backend; # $not", False),
        ("CVE-2026-113425", "mail_block", "mail {", True),
    ],
)
def test_recorded_exposure_patterns(cve_id, condition, line, matches):
    assert bool(re.search(recorded_pattern(cve_id, condition), line, re.MULTILINE)) is matches


def test_proxy_nginx_conf_resolver_is_seen():
    """proxy/nginx.conf's own resolver is part of every install's config."""
    conf = (ROOT / "proxy" / "nginx.conf").read_text()
    assert re.search(recorded_pattern("CVE-2026-123634", "resolver"), conf, re.MULTILINE)


def cve_exposure(cve_id: str) -> list:
    data = json.loads((CVE_DIR / f"{cve_id}.json").read_text())
    for cond in data["exposure"]:
        cond["text"] = "cfg"
    return data["exposure"]


# ── Plans ───────────────────────────────────────────────────────────────────────────────────────


def plan_for(f, **overrides):
    results = cve.evaluate([advisory(**overrides)], f)
    return cve.plan(results, f)


def test_exposed_with_a_mitigation_plans_it():
    assert plan_for(facts()) == ({"disable_http2": ["CVE-2099-0001"]}, [], [])


def test_an_upgrade_that_fixes_it_plans_nothing():
    assert plan_for(facts(target="1.31.9")) == ({}, [], [])


def test_an_upgrade_that_doesnt_fix_it_still_plans_the_mitigation():
    assert plan_for(facts(target="1.31.8"))[0] == {"disable_http2": ["CVE-2099-0001"]}


def test_fixed_with_the_mitigation_on_reverts_it():
    assert plan_for(facts(version="1.31.9", cfg="", active={"disable_http2"})) == ({}, ["disable_http2"], [])


def test_mitigated_and_still_affected_keeps_it():
    assert plan_for(facts(cfg="", active={"disable_http2"})) == ({}, [], [])


def test_unknown_mitigation_state_never_reverts():
    assert plan_for(facts(version="1.31.9", cfg="", active=None)) == ({}, [], [])


def test_an_unknown_version_never_reverts():
    assert plan_for(facts(version=None, cfg="", active={"disable_http2"})) == ({}, [], [])


def test_exposed_without_a_supported_mitigation_is_reported():
    assert plan_for(facts(), mitigations=[]) == ({}, [], ["CVE-2099-0001"])


def test_mitigation_on_but_custom_config_still_exposes():
    # e.g. an advanced_config snippet with its own `http2 on;`
    assert plan_for(facts(active={"disable_http2"})) == ({}, [], ["CVE-2099-0001"])


# ── Validation ──────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"id": "CVE-2099-0002"}, "doesn't match the file name"),
        ({"id": "nonsense"}, "id must look like"),
        ({"severity": "urgent"}, "severity"),
        ({"published": "soon"}, "published"),
        ({"colour": "red"}, "unknown key 'colour'"),
        ({"affects": {"component": "nginx", "fixed": ["1.x"]}}, "isn't a version"),
        ({"exposure": [{"id": "a", "text": "cfg", "pattern": "(", "describe": "x"}], "mitigations": []}, "compile"),
        ({"mitigations": [{"name": "m", "removes": ["nope"], "describe": "x"}]}, "no exposure condition 'nope'"),
        ({"mitigations": [{"name": "m", "removes": [], "describe": "x"}]}, "removes must list"),
        ({"references": ["http://insecure"]}, "https://"),
    ],
)
def test_validation_errors(overrides, message):
    _, errors = cve.validate_manifest(manifest(**overrides), "CVE-2099-0001")
    assert any(message in e for e in errors), errors


def test_an_invalid_file_is_reported_and_skipped(tmp_path):
    (tmp_path / "CVE-2099-0001.json").write_text(json.dumps(manifest()))
    (tmp_path / "CVE-2099-0003.json").write_text("{not json")
    advisories, invalid = cve.load_dir(tmp_path)
    assert [a.id for a in advisories] == ["CVE-2099-0001"]
    assert list(invalid) == ["CVE-2099-0003.json"]
    assert cve.main(["validate", str(tmp_path)]) == 1


# ── The CLI the upgrade script reads ────────────────────────────────────────────────────────────


def test_cli_plan_lines(tmp_path, capsys):
    advisories = tmp_path / "cve"  # facts live outside it: every *.json in it is read as an advisory
    advisories.mkdir()
    (advisories / "CVE-2099-0001.json").write_text(json.dumps(manifest()))
    cfg = tmp_path / "cfg.txt"
    cfg.write_text("server {\n    http2 on;\n}\n")
    active = tmp_path / "active.json"
    active.write_text('{"active": []}')
    code = cve.main(
        [
            *["evaluate", str(advisories), "--version", "nginx=1.25.3", "--text", f"cfg={cfg}"],
            *["--active-mitigations", str(active), "--supported-mitigation", "disable_http2"],
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "@@apply disable_http2 CVE-2099-0001" in out.splitlines()
    assert "@@summary vulnerable=1 unknown=0 mitigated=0 not_exposed=0 fixed=0 invalid=0" in out


# ── Against config this API generates ───────────────────────────────────────────────────────────


def https_host():
    host = MagicMock(spec=ProxyHost)
    for key, value in {
        "id": "host-1",
        "domain_names": ["shop.example.com"],
        "forward_scheme": "http",
        "forward_host": "10.0.0.5",
        "forward_port": 8080,
        "ssl_enabled": True,
        "ssl_forced": True,
        "http2_support": True,
        "hsts_enabled": False,
        "hsts_subdomains": False,
        "block_common_exploits": False,
        "websocket_support": False,
        "cache_enabled": False,
        "access_list_id": None,
        "auth_wall_id": None,
        "custom_nginx_config": "",
        "advanced_config": "",
        "upstream_servers": [],
        "locations": [],
        "rate_limit_requests": 100,
        "rate_limit_period": "1s",
    }.items():
        setattr(host, key, value)
    return host


@pytest.fixture
def no_mitigations():
    openresty_service.set_cve_mitigations(())
    yield
    openresty_service.set_cve_mitigations(())


@pytest.mark.parametrize("cve_id", ["CVE-2026-123007", "CVE-2026-123633"])
def test_generated_http2_config_is_exposed_until_mitigated(cve_id, no_mitigations):
    advisories, _ = cve.load_dir(CVE_DIR)
    adv = next(a for a in advisories if a.id == cve_id)

    def check(active):
        f = cve.Facts(
            versions={"nginx": "1.25.3"},
            texts={"nginx_config": generate_server_block(https_host(), MagicMock())},
            active=set(active),
            supported={"disable_http2"},
        )
        return cve.evaluate([adv], f)[0].status

    assert check(()) == cve.VULNERABLE
    openresty_service.set_cve_mitigations({"disable_http2"})
    assert check({"disable_http2"}) == cve.MITIGATED
