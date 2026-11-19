#!/usr/bin/env python3
"""Ghostwire CVE registry engine: checks this install against the advisories in cve/.

    ghostwire_cve.py validate CVE_DIR
    ghostwire_cve.py evaluate CVE_DIR [facts...] [--json]

Facts are what the upgrade script measured on the running install (the engine runs nothing itself):

    --version NAME=VER          a component's running version (nginx=1.25.3); repeatable
    --target-version NAME=VER   the same component after the planned upgrade; repeatable
    --text NAME=PATH            a text fact, e.g. nginx_config=/tmp/openresty-T.conf; repeatable
    --active-mitigations PATH   JSON {"active": ["disable_http2", ...]} from the API; unreadable = unknown
    --supported-mitigation NAME a mitigation this app's upgrade script can apply; repeatable

evaluate prints a report for people, then the plan as lines the script reads:

    @@apply NAME CVE-A,CVE-B    turn a mitigation on (a CVE it covers is exposed and not fixed)
    @@reapply NAME CVE-A        apply one again: it's on, yet CVE-A still reads exposed (regenerates)
    @@revert NAME               turn a mitigation off (nothing it covers is still affected)
    @@exposed CVE-A             a CVE this install is exposed to, with no mitigation planned or active
    @@summary key=n ...         counts, for the log and notifications

Stdlib only, Python 3.10+: it runs on the host or in the API image. The format is in cve/README.md.
Shared by every Ghostwire app's upgrade script: change it in all of them together.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

SCHEMA = 1
SEVERITIES = ("critical", "high", "medium", "low")
ID_RE = re.compile(r"^(CVE-\d{4}-\d{4,}|GHSA(-[a-z0-9]{4}){3})$")
NAME_RE = re.compile(r"^[a-z0-9_]+$")
VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+)*)$")
TOP_KEYS = {"schema", "id", "aliases", "title", "severity", "published", "summary", "references"}
TOP_KEYS |= {"affects", "exposure", "fix", "mitigations"}
REQUIRED = {"schema", "id", "title", "severity", "published", "summary", "affects"}

# Statuses, worst first.
VULNERABLE = "vulnerable"  # an affected version, and every exposure condition holds
UNKNOWN = "unknown"  # a fact the advisory needs couldn't be measured: never read as safe
MITIGATED = "mitigated"  # an affected version, kept unexposed by a mitigation that's on
NOT_EXPOSED = "not_exposed"  # an affected version, but this install doesn't use the affected feature
FIXED = "fixed"  # the running version isn't in the affected range
ORDER = (VULNERABLE, UNKNOWN, MITIGATED, NOT_EXPOSED, FIXED)


def parse_version(text: str | None) -> tuple[int, ...] | None:
    if not isinstance(text, str):
        return None
    m = VERSION_RE.match(text.strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def is_fixed(v: tuple[int, ...], fixed: list[tuple[int, ...]]) -> bool:
    """Fixed on its own branch (1.30.8 against 1.30.7), or newer than every fix (1.32.0)."""
    if not fixed:
        return False
    if v >= max(fixed):
        return True
    return any(v[: len(f) - 1] == f[:-1] and v >= f for f in fixed)


def in_range(v: tuple[int, ...], introduced: tuple[int, ...] | None, fixed: list[tuple[int, ...]]) -> bool:
    if introduced is not None and v < introduced:
        return False
    return not is_fixed(v, fixed)


# ── Loading and validating ──────────────────────────────────────────────────────────────────────


@dataclass
class Advisory:
    id: str
    title: str
    severity: str
    summary: str
    component: str
    introduced: tuple[int, ...] | None
    fixed: list[tuple[int, ...]]
    fixed_text: list[str]
    exposure: list[dict]
    mitigations: list[dict]
    fix_note: str = ""
    aliases: list[str] = field(default_factory=list)


def _check(errors: list[str], ok: bool, message: str) -> bool:
    if not ok:
        errors.append(message)
    return ok


def validate_manifest(data: object, stem: str) -> tuple[Advisory | None, list[str]]:
    """Every problem with one manifest, so a bad file is reported whole rather than one error a run."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return None, ["the file isn't a JSON object"]
    for key in sorted(REQUIRED - data.keys()):
        errors.append(f"missing {key!r}")
    for key in sorted(data.keys() - TOP_KEYS):
        errors.append(f"unknown key {key!r} (a typo?)")
    _check(errors, data.get("schema") == SCHEMA, f"schema must be {SCHEMA}")

    cve_id = data.get("id")
    if _check(errors, isinstance(cve_id, str) and bool(ID_RE.match(cve_id)), "id must look like CVE-2026-12345"):
        _check(errors, cve_id == stem, f"id {cve_id} doesn't match the file name {stem}.json")
    for key in ("title", "summary"):
        _check(errors, isinstance(data.get(key), str) and bool(data.get(key, "").strip()), f"{key} must be text")
    _check(errors, data.get("severity") in SEVERITIES, f"severity must be one of {', '.join(SEVERITIES)}")
    try:
        date.fromisoformat(data.get("published", ""))
    except (TypeError, ValueError):
        errors.append("published must be a date (YYYY-MM-DD)")
    aliases = data.get("aliases", [])
    _check(errors, isinstance(aliases, list) and all(isinstance(a, str) for a in aliases), "aliases must be text")
    refs = data.get("references", [])
    _check(
        errors,
        isinstance(refs, list) and all(isinstance(r, str) and r.startswith("https://") for r in refs),
        "references must be https:// links",
    )

    affects = data.get("affects")
    component, introduced, fixed, fixed_text = "", None, [], []
    if _check(errors, isinstance(affects, dict), "affects must be an object"):
        for key in sorted(affects.keys() - {"component", "introduced", "fixed"}):
            errors.append(f"affects: unknown key {key!r}")
        component = affects.get("component", "")
        _check(errors, isinstance(component, str) and bool(NAME_RE.match(component)), "affects.component: a-z0-9_")
        if affects.get("introduced") is not None:
            introduced = parse_version(affects["introduced"])
            _check(errors, introduced is not None, "affects.introduced must be a version like 1.9.5, or null")
        fixed_text = affects.get("fixed", [])
        if _check(errors, isinstance(fixed_text, list), "affects.fixed must be a list of versions"):
            for v in fixed_text:
                parsed = parse_version(v)
                if _check(errors, parsed is not None, f"affects.fixed: {v!r} isn't a version"):
                    fixed.append(parsed)

    exposure = data.get("exposure", [])
    condition_ids: set[str] = set()
    if _check(errors, isinstance(exposure, list), "exposure must be a list"):
        for i, cond in enumerate(exposure):
            where = f"exposure[{i}]"
            if not _check(errors, isinstance(cond, dict), f"{where} must be an object"):
                continue
            for key in sorted(cond.keys() - {"id", "text", "pattern", "describe"}):
                errors.append(f"{where}: unknown key {key!r}")
            cid = cond.get("id")
            if _check(errors, isinstance(cid, str) and bool(NAME_RE.match(cid)), f"{where}.id: a-z0-9_"):
                _check(errors, cid not in condition_ids, f"{where}.id {cid!r} is used twice")
                condition_ids.add(cid)
            text = cond.get("text")
            _check(errors, isinstance(text, str) and bool(NAME_RE.match(text)), f"{where}.text: a-z0-9_")
            _check(errors, isinstance(cond.get("describe"), str), f"{where}.describe must be text")
            try:
                re.compile(cond.get("pattern"), re.MULTILINE)
            except (TypeError, re.error) as e:
                errors.append(f"{where}.pattern doesn't compile: {e}")

    mitigations = data.get("mitigations", [])
    if _check(errors, isinstance(mitigations, list), "mitigations must be a list"):
        for i, mit in enumerate(mitigations):
            where = f"mitigations[{i}]"
            if not _check(errors, isinstance(mit, dict), f"{where} must be an object"):
                continue
            for key in sorted(mit.keys() - {"name", "removes", "describe"}):
                errors.append(f"{where}: unknown key {key!r}")
            name = mit.get("name")
            _check(errors, isinstance(name, str) and bool(NAME_RE.match(name)), f"{where}.name: a-z0-9_")
            _check(errors, isinstance(mit.get("describe"), str), f"{where}.describe must be text")
            removes = mit.get("removes")
            # A mitigation works by making an exposure condition false; it has to say which.
            if _check(
                errors,
                isinstance(removes, list) and bool(removes),
                f"{where}.removes must list the exposure ids it turns off",
            ):
                for cid in removes:
                    _check(errors, cid in condition_ids, f"{where}.removes: no exposure condition {cid!r}")

    fix = data.get("fix", {})
    if _check(errors, isinstance(fix, dict), "fix must be an object"):
        for key in sorted(fix.keys() - {"note"}):
            errors.append(f"fix: unknown key {key!r}")

    if errors:
        return None, errors
    return (
        Advisory(
            id=cve_id,
            title=data["title"].strip(),
            severity=data["severity"],
            summary=data["summary"].strip(),
            component=component,
            introduced=introduced,
            fixed=fixed,
            fixed_text=list(fixed_text),
            exposure=exposure,
            mitigations=mitigations,
            fix_note=fix.get("note", ""),
            aliases=aliases,
        ),
        [],
    )


def load_dir(cve_dir: Path) -> tuple[list[Advisory], dict[str, list[str]]]:
    advisories, invalid = [], {}
    for path in sorted(cve_dir.glob("*.json")):
        if path.name == "schema.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            invalid[path.name] = [f"can't read it as JSON: {e}"]
            continue
        advisory, errors = validate_manifest(data, path.stem)
        if errors:
            invalid[path.name] = errors
        else:
            advisories.append(advisory)
    return advisories, invalid


# ── Evaluating ──────────────────────────────────────────────────────────────────────────────────


@dataclass
class Facts:
    versions: dict[str, str] = field(default_factory=dict)
    target_versions: dict[str, str] = field(default_factory=dict)
    texts: dict[str, str] = field(default_factory=dict)
    active: set[str] | None = None  # None: couldn't ask, so nothing can be called mitigated or reverted
    supported: set[str] = field(default_factory=set)


@dataclass
class Result:
    advisory: Advisory
    status: str
    version: str | None
    reasons: list[str]
    target_status: str | None = None  # after the planned upgrade, when that's known
    target_version: str | None = None


def exposure_of(adv: Advisory, facts: Facts) -> tuple[bool | None, list[str], set[str]]:
    """(exposed?, one line per condition, ids of the conditions that don't hold)."""
    lines, failing, unknown = [], set(), False
    for cond in adv.exposure:
        text = facts.texts.get(cond["text"])
        if text is None:
            unknown = True
            lines.append(f"{cond['describe']}: unknown (no {cond['text']} to look at)")
        elif re.search(cond["pattern"], text, re.MULTILINE):
            lines.append(f"{cond['describe']}: yes")
        else:
            failing.add(cond["id"])
            lines.append(f"{cond['describe']}: no")
    if failing:
        return False, lines, failing
    return (None if unknown else True), lines, failing


def status_for(adv: Advisory, version: str | None, facts: Facts) -> tuple[str, list[str]]:
    parsed = parse_version(version)
    if parsed is None:
        what = f"{adv.component} version unknown" if version is None else f"can't read {version!r} as a version"
        return UNKNOWN, [what]
    if not in_range(parsed, adv.introduced, adv.fixed):
        return FIXED, []
    exposed, lines, failing = exposure_of(adv, facts)
    if exposed is True:
        return VULNERABLE, lines
    if exposed is None:
        return UNKNOWN, lines
    if facts.active is not None:
        for mit in adv.mitigations:
            if mit["name"] in facts.active and failing & set(mit["removes"]):
                return MITIGATED, [*lines, f"kept off by mitigation {mit['name']}"]
    return NOT_EXPOSED, lines


def evaluate(advisories: list[Advisory], facts: Facts) -> list[Result]:
    results = []
    for adv in advisories:
        version = facts.versions.get(adv.component)
        status, reasons = status_for(adv, version, facts)
        result = Result(adv, status, version, reasons)
        target = facts.target_versions.get(adv.component)
        if target is not None and target != version:
            result.target_version = target
            result.target_status = status_for(adv, target, facts)[0]
        results.append(result)
    results.sort(key=lambda r: (ORDER.index(r.status), SEVERITIES.index(r.advisory.severity), r.advisory.id))
    return results


def effective(r: Result) -> str:
    """What the install will be once the planned upgrade (if any) has run."""
    return r.target_status if r.target_status is not None else r.status


@dataclass
class Plan:
    apply: dict[str, list[str]] = field(default_factory=dict)  # turn on → the CVEs it's for
    revert: list[str] = field(default_factory=list)  # turn off: nothing it covers is affected
    exposed: list[str] = field(default_factory=list)  # exposed CVEs no mitigation here clears (yet)
    # On already, yet still exposed: the config wasn't regenerated since (an older release wrote
    # it), or a custom snippet re-enables what it turns off. Applying it again regenerates the
    # config once; whatever is still exposed after that is the snippet's doing.
    reapply: dict[str, list[str]] = field(default_factory=dict)


def plan(results: list[Result], facts: Facts) -> Plan:
    p = Plan()
    for r in results:
        if r.status != VULNERABLE or effective(r) == FIXED:
            continue
        names = [m["name"] for m in r.advisory.mitigations if m["name"] in facts.supported]
        on = [n for n in names if facts.active is not None and n in facts.active]
        if on:
            p.reapply.setdefault(on[0], []).append(r.advisory.id)
            p.exposed.append(r.advisory.id)
        elif names:
            p.apply.setdefault(names[0], []).append(r.advisory.id)
        else:
            p.exposed.append(r.advisory.id)
    if facts.active is not None:
        for name in sorted(facts.active & facts.supported):
            still_needed = any(
                effective(r) != FIXED and any(m["name"] == name for m in r.advisory.mitigations) for r in results
            )
            if not still_needed and name not in p.apply:
                p.revert.append(name)
    return p


# ── Output ──────────────────────────────────────────────────────────────────────────────────────

LABELS = {
    VULNERABLE: "EXPOSED",
    UNKNOWN: "unknown",
    MITIGATED: "mitigated",
    NOT_EXPOSED: "not exposed",
    FIXED: "fixed",
}


def describe_mitigation(adv: Advisory, name: str) -> str:
    return next((m["describe"] for m in adv.mitigations if m["name"] == name), name)


def print_report(results, invalid, p: Plan, out=None) -> None:
    out = out or sys.stdout  # looked up now, not at import, so a redirected stdout is honoured

    def say(line: str = "") -> None:
        print(line, file=out)

    if not results and not invalid:
        say("  No advisories recorded.")
    for r in results:
        adv = r.advisory
        alias = f" ({', '.join(adv.aliases)})" if adv.aliases else ""
        version = f"{adv.component} {r.version}" if r.version else adv.component
        say(f"  {adv.id:<17} {adv.severity:<8} {LABELS[r.status]:<11} {version}: {adv.title}{alias}")
        if r.status == FIXED and r.target_status is None:
            continue
        for reason in r.reasons:
            say(f"  {'':<17} {reason}")
        if r.target_status is not None:
            say(f"  {'':<17} after this upgrade ({adv.component} {r.target_version}): {LABELS[r.target_status]}")
        if effective(r) != FIXED:
            fixed = ", ".join(adv.fixed_text) or "none yet"
            note = f" {adv.fix_note}" if adv.fix_note else ""
            say(f"  {'':<17} fixed in {adv.component} {fixed}.{note}")
    for name, errors in invalid.items():
        say(f"  {name}: not a valid advisory, skipped:")
        for e in errors:
            say(f"  {'':<17} {e}")

    by_id = {r.advisory.id: r.advisory for r in results}
    for name, ids in p.apply.items():
        say(f"  → turn on {name} for {', '.join(ids)}: {describe_mitigation(by_id[ids[0]], name)}")
    for name, ids in p.reapply.items():
        say(f"  → apply {name} again for {', '.join(ids)}: it's on, but the live config still has what it removes")
    for name in p.revert:
        say(f"  → turn off {name}: nothing it covers is still affected")
    overridden = {i for ids in p.reapply.values() for i in ids}
    for name, ids in p.reapply.items():
        say(
            f"  ! {name} is on, yet {', '.join(ids)} read exposed: the live config still turns on what it"
            " turns off (a host's custom snippet, or a config written before it was on)"
        )
    plain = [i for i in p.exposed if i not in overridden]
    if plain:
        say(f"  ! exposed with no mitigation here: {', '.join(plain)} (see the advisories in cve/)")


def print_plan(results, invalid, p: Plan, out=None) -> None:
    out = out or sys.stdout
    for name, ids in p.apply.items():
        print(f"@@apply {name} {','.join(ids)}", file=out)
    for name, ids in p.reapply.items():
        print(f"@@reapply {name} {','.join(ids)}", file=out)
    for name in p.revert:
        print(f"@@revert {name}", file=out)
    for cve_id in p.exposed:
        print(f"@@exposed {cve_id}", file=out)
    counts = {s: sum(r.status == s for r in results) for s in ORDER}
    counts["invalid"] = len(invalid)
    print("@@summary " + " ".join(f"{k}={v}" for k, v in counts.items()), file=out)


def as_json(results, invalid, p: Plan) -> dict:
    return {
        "advisories": [
            {
                "id": r.advisory.id,
                "aliases": r.advisory.aliases,
                "title": r.advisory.title,
                "severity": r.advisory.severity,
                "component": r.advisory.component,
                "version": r.version,
                "status": r.status,
                "reasons": r.reasons,
                "target_version": r.target_version,
                "target_status": r.target_status,
                "fixed_in": r.advisory.fixed_text,
                "fix_note": r.advisory.fix_note,
                "mitigations": [m["name"] for m in r.advisory.mitigations],
            }
            for r in results
        ],
        "invalid": invalid,
        "plan": {"apply": p.apply, "reapply": p.reapply, "revert": p.revert, "exposed": p.exposed},
    }


# ── CLI ─────────────────────────────────────────────────────────────────────────────────────────


def _pairs(values: list[str], what: str) -> dict[str, str]:
    out = {}
    for item in values or []:
        name, sep, value = item.partition("=")
        if not sep or not NAME_RE.match(name):
            raise SystemExit(f"--{what} wants NAME=VALUE, got {item!r}")
        out[name] = value.strip()
    return out


def read_facts(args: argparse.Namespace) -> Facts:
    facts = Facts(
        versions={k: v for k, v in _pairs(args.version, "version").items() if v},
        target_versions={k: v for k, v in _pairs(args.target_version, "target-version").items() if v},
        supported=set(args.supported_mitigation or []),
    )
    for name, path in _pairs(args.text, "text").items():
        # Missing: conditions on it come out unknown, never "not exposed".
        with contextlib.suppress(OSError):
            facts.texts[name] = Path(path).read_text(encoding="utf-8", errors="replace")
    if args.active_mitigations:
        try:
            active = json.loads(Path(args.active_mitigations).read_text(encoding="utf-8")).get("active")
            if isinstance(active, list) and all(isinstance(a, str) for a in active):
                facts.active = set(active)
        except (OSError, ValueError, AttributeError):
            pass
    return facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate", help="check every manifest; exit 1 if any is invalid")
    v.add_argument("cve_dir", type=Path)
    e = sub.add_parser("evaluate", help="report this install's status and the plan")
    e.add_argument("cve_dir", type=Path)
    e.add_argument("--version", action="append", metavar="NAME=VER")
    e.add_argument("--target-version", action="append", metavar="NAME=VER")
    e.add_argument("--text", action="append", metavar="NAME=PATH")
    e.add_argument("--active-mitigations", metavar="PATH")
    e.add_argument("--supported-mitigation", action="append", metavar="NAME")
    e.add_argument("--json", action="store_true", help="one JSON document instead of the report and plan")
    args = parser.parse_args(argv)

    if not args.cve_dir.is_dir():
        print(f"{args.cve_dir} isn't a directory", file=sys.stderr)
        return 2
    advisories, invalid = load_dir(args.cve_dir)

    if args.command == "validate":
        for name, errors in invalid.items():
            for err in errors:
                print(f"{args.cve_dir / name}: {err}")
        print(f"{len(advisories)} valid, {len(invalid)} invalid")
        return 1 if invalid else 0

    facts = read_facts(args)
    results = evaluate(advisories, facts)
    p = plan(results, facts)
    if args.json:
        print(json.dumps(as_json(results, invalid, p), indent=2))
    else:
        print_report(results, invalid, p)
        print_plan(results, invalid, p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
