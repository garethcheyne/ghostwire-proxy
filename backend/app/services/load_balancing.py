"""
Load-balancing rules shared by the API, the config generator and the health loop.

Kept free of database and FastAPI imports so the same checks run on a saved
host, on a create/update payload and on the editor's live preview.

nginx references (ngx_http_upstream_module):
- `backup` "cannot be used along with the hash, ip_hash, and random load
  balancing methods", so it is only offered with round robin and least_conn.
- `down` is allowed with every method; with ip_hash/hash it is the documented
  way to take a server out while keeping the other clients' mapping.
- weights are honoured by every method (ip_hash since nginx 1.3.1).
- the method directive must come before `keepalive` in the upstream block.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any, Iterable, Optional

# Method key -> the directive it renders (None = nginx's default round robin).
LB_METHODS: dict[str, Optional[str]] = {
    "round_robin": None,
    "least_conn": "least_conn;",
    "ip_hash": "ip_hash;",
    "hash_uri": "hash $request_uri consistent;",
    "random_two": "random two least_conn;",
}

LB_METHOD_LABELS = {
    "round_robin": "Round robin",
    "least_conn": "Least connections",
    "ip_hash": "IP hash",
    "hash_uri": "URI hash",
    "random_two": "Random (two choices)",
}

# Methods nginx allows `backup` servers with.
BACKUP_METHODS = frozenset({"round_robin", "least_conn"})

HEALTH_CHECK_TYPES = ("http", "tcp")

# Defaults the generator leaves implicit, so a server line only carries what
# was actually changed.
DEFAULT_WEIGHT = 1
DEFAULT_MAX_FAILS = 3
DEFAULT_FAIL_TIMEOUT = 30
DEFAULT_KEEPALIVE = 32

# Most attempts nginx makes for one request when a server fails.
MAX_NEXT_UPSTREAM_TRIES = 3

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?"
    r"(\.[A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?)*\.?$"
)


def normalize_upstream_host(value: str) -> str:
    """Validate an upstream host (IPv4, IPv6 or DNS name) and return it clean.

    It is written straight into the nginx config, so anything that isn't a plain
    address or hostname (spaces, `;`, braces, a scheme, a port) is refused.
    """
    v = (value or "").strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    if not v:
        raise ValueError("Host is required")
    try:
        return str(ipaddress.ip_address(v))
    except ValueError:
        pass
    if not _HOSTNAME_RE.match(v):
        raise ValueError(
            f"'{value}' is not a valid IP address or hostname (no scheme, port or path)"
        )
    return v.lower()


def format_server_address(host: str, port: int) -> str:
    """host:port as nginx wants it; IPv6 literals go in brackets."""
    if ":" in host and not host.startswith("["):
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def validate_health_check_path(value: str) -> str:
    v = (value or "").strip() or "/"
    if not v.startswith("/") or v.startswith("//"):
        raise ValueError("Health check path must start with a single '/'")
    if len(v) > 255:
        raise ValueError("Health check path is too long (255 characters max)")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in v) or "#" in v:
        raise ValueError("Health check path can't contain spaces, control characters or '#'")
    return v


def _get(server: Any, name: str, default: Any = None) -> Any:
    if isinstance(server, dict):
        return server.get(name, default)
    return getattr(server, name, default)


def check_lb_rules(method: Optional[str], servers: Iterable[Any]) -> tuple[list[str], list[str]]:
    """Cross-field checks for a host's upstream group.

    Returns (errors, warnings). Errors block a save; warnings are shown in the
    editor only. An empty server list is valid: the host is a single backend.
    """
    errors: list[str] = []
    warnings: list[str] = []
    method = method or "round_robin"
    servers = list(servers)

    if method not in LB_METHODS:
        errors.append(f"Unknown balancing method '{method}'")
        return errors, warnings
    if not servers:
        return errors, warnings

    enabled = [s for s in servers if _get(s, "enabled", True)]
    primaries = [s for s in enabled if not _get(s, "backup", False)]
    backups = [s for s in enabled if _get(s, "backup", False)]

    if not primaries:
        errors.append("At least one enabled server that isn't a backup is required")

    if backups and method not in BACKUP_METHODS:
        errors.append(
            f"{LB_METHOD_LABELS[method]} can't be combined with backup servers "
            "(an nginx restriction). Use round robin or least connections, or "
            "untick Backup."
        )

    seen: set[str] = set()
    for s in servers:
        key = format_server_address(str(_get(s, "host", "")).lower(), _get(s, "port", 0))
        if key in seen:
            errors.append(f"{key} is listed more than once")
        seen.add(key)

    if primaries and all(_get(s, "down", False) for s in primaries):
        if backups:
            warnings.append("Every primary server is marked down: all traffic goes to the backups")
        else:
            warnings.append("Every server is marked down: visitors will get 502 Bad Gateway")

    if not enabled:
        return errors, warnings
    if len(enabled) == 1:
        warnings.append("Only one server is enabled, so there is nothing to balance yet")

    return errors, warnings
