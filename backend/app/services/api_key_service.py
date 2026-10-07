"""Scoped API keys: minting, checking, and deciding what a key may call.

Keys look like `gwp_<prefix>_<secret>`:

  * `prefix` — 10 lowercase letters/digits, stored in clear and unique; finds the row and is what
    the UI shows.
  * `secret` — 40 characters from [A-Za-z0-9] (~238 bits). Never stored.

The row keeps SHA-256(full key). A presented key is hashed and compared with
`hmac.compare_digest`, and an unknown prefix is compared against a dummy hash so a miss costs the
same as a wrong secret.

What a key may call is decided here, centrally, from the request's method and path
(`required_scope`), so every route that authenticates through `get_current_user` is covered,
including ones added later: anything not listed is refused to keys (default deny). Routes that
could hand over the instance — users, API keys, two-factor, updates, container actions, backup
restore/upload/download, the kill switch — never accept a key, whatever its scopes.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import string
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.user import User

logger = logging.getLogger("ghostwire.api_keys")

KEY_PREFIX = "gwp_"
PREFIX_LENGTH = 10
SECRET_LENGTH = 40
_PREFIX_ALPHABET = string.ascii_lowercase + string.digits
_SECRET_ALPHABET = string.ascii_letters + string.digits
_KEY_RE = re.compile(r"^gwp_([a-z0-9]{%d})_([A-Za-z0-9]{%d})$" % (PREFIX_LENGTH, SECRET_LENGTH))

# Last-used is written at most this often per key, not on every request.
LAST_USED_WRITE_INTERVAL = timedelta(seconds=60)

# ---------------------------------------------------------------------------
# Scopes
# ---------------------------------------------------------------------------

READ = "read"
ADMIN = "admin"
SESSION_ONLY = "session-only"

# Ordered for display. `admin` includes every other scope.
SCOPES: dict[str, str] = {
    "read": "Read proxy hosts, upstreams, certificates, access lists, auth walls, security rules, "
            "traffic, analytics, health and the audit log. Dry-run previews of config changes.",
    "write:proxy-hosts": "Create, change, enable, disable and delete proxy hosts and their locations, "
                         "including the load-balancing method and replacing the whole upstream list.",
    "write:upstreams": "Add, change, remove and health-check a host's individual upstream servers.",
    "write:certificates": "Request, upload, renew and delete TLS certificates.",
    "write:access": "Change access lists and auth walls.",
    "write:security": "Change WAF rules and thresholds, threat-actor blocks, rate limits, GeoIP rules, "
                      "known IPs, honeypot traps and security presets.",
    "write:nginx": "Test the nginx configuration and regenerate/reload OpenResty.",
    "admin": "Everything above, plus settings, DNS providers, firewall connectors, alerts, reports, "
             "backups (list/create), system maintenance and update/container status. Never users, "
             "API keys, two-factor, updates, backup restore or the kill switch.",
}

_READ_METHODS = {"GET", "HEAD", "OPTIONS"}
_ANY = None  # matches every method

# (methods or None for any, path regex, scope). First match wins; no match = refused.
_RULES: list[tuple[set[str] | None, re.Pattern, str]] = [
    # Never through a key.
    (_ANY, re.compile(r"^/api/api-keys(/|$)"), SESSION_ONLY),
    (_ANY, re.compile(r"^/api/admin-mfa(/|$)"), SESSION_ONLY),
    (_READ_METHODS, re.compile(r"^/api/users/me/?$"), READ),
    (_ANY, re.compile(r"^/api/users(/|$)"), SESSION_ONLY),
    (_ANY, re.compile(r"^/api/backups/(restore|upload)/?$"), SESSION_ONLY),
    (_ANY, re.compile(r"^/api/backups/[^/]+/download/?$"), SESSION_ONLY),
    (_ANY, re.compile(r"^/api/system/kill-switch/?$"), SESSION_ONLY),
    (None, re.compile(r"^/api/updates/(app|base-image|rollback|check-now|settings)(/|$)"), "_updates"),
    (None, re.compile(r"^/api/containers/auto-update(/|$)"), "_containers"),

    # Dry runs render config without changing anything.
    ({"POST"}, re.compile(r"^/api/config/preview/?$"), READ),
    ({"POST"}, re.compile(r"^/api/proxy-hosts/upstream-preview/?$"), READ),

    # nginx operations.
    ({"POST"}, re.compile(r"^/api/config/(test|reload)/?$"), "write:nginx"),
    ({"POST"}, re.compile(r"^/api/settings/reload-nginx/?$"), "write:nginx"),

    # Writes, by area.
    (None, re.compile(r"^/api/proxy-hosts/[^/]+/upstreams(/|$)"), "_write:upstreams"),
    (None, re.compile(r"^/api/proxy-hosts(/|$)"), "_write:proxy-hosts"),
    (None, re.compile(r"^/api/certificates(/|$)"), "_write:certificates"),
    (None, re.compile(r"^/api/(access-lists|auth-walls)(/|$)"), "_write:access"),
    (None, re.compile(r"^/api/(waf|rate-limits|geoip|known-ips|honeypot|presets)(/|$)"), "_write:security"),

    # Read-only areas.
    (_READ_METHODS, re.compile(r"^/api/(traffic|analytics|search|audit-logs)(/|$)"), READ),
    (_READ_METHODS, re.compile(r"^/api/reports/hosts/[^/]+/?$"), READ),
    (_READ_METHODS, re.compile(r"^/api/system/(status|metrics|throughput|containers|database-health)/?$"), READ),

    # The rest of the admin surface.
    (_ANY, re.compile(r"^/api/(settings|dns|firewalls|alerts|reports|backups|system|traffic|updates|containers)(/|$)"), ADMIN),
]


def required_scope(method: str, path: str) -> str | None:
    """The scope a key needs for this request; SESSION_ONLY or None means keys are refused."""
    method = method.upper()
    for methods, pattern, scope in _RULES:
        if methods is not None and method not in methods:
            continue
        if not pattern.match(path):
            continue
        # "_write:x" rules: reads need `read`, anything else the write scope.
        if scope.startswith("_write:"):
            return READ if method in _READ_METHODS else scope[1:]
        # Dangerous areas: reads are admin, writes never via a key.
        if scope in ("_updates", "_containers"):
            return ADMIN if method in _READ_METHODS else SESSION_ONLY
        return scope
    return None


def has_scope(granted: list[str] | None, needed: str) -> bool:
    granted = granted or []
    return needed in granted or ADMIN in granted


def normalize_scopes(scopes: list[str]) -> list[str]:
    unknown = [s for s in scopes if s not in SCOPES]
    if unknown:
        raise ValueError(f"Unknown scope(s): {', '.join(unknown)}")
    if not scopes:
        raise ValueError("Choose at least one scope")
    # Every key can read: a key that changes things needs to see them, and dry runs are reads.
    wanted = set(scopes) | {READ}
    # Stable order, no duplicates.
    return [s for s in SCOPES if s in wanted]


# ---------------------------------------------------------------------------
# Minting and hashing
# ---------------------------------------------------------------------------

def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


_DUMMY_HASH = hash_key("gwp_" + "0" * PREFIX_LENGTH + "_" + "0" * SECRET_LENGTH)


def generate_key() -> tuple[str, str]:
    """A new (full key, prefix)."""
    prefix = "".join(secrets.choice(_PREFIX_ALPHABET) for _ in range(PREFIX_LENGTH))
    secret = "".join(secrets.choice(_SECRET_ALPHABET) for _ in range(SECRET_LENGTH))
    return f"{KEY_PREFIX}{prefix}_{secret}", prefix


def looks_like_key(token: str | None) -> bool:
    return bool(token) and token.startswith(KEY_PREFIX)


async def create_key(
    db: AsyncSession,
    user: User,
    name: str,
    scopes: list[str],
    expires_in_days: int | None,
) -> tuple[ApiKey, str]:
    """Create a key; returns the row and the full key (shown once, never stored)."""
    scopes = normalize_scopes(scopes)
    for _ in range(5):
        key, prefix = generate_key()
        clash = await db.execute(select(ApiKey.id).where(ApiKey.prefix == prefix))
        if clash.scalar_one_or_none() is None:
            break
    else:  # pragma: no cover - 36^10 prefixes
        raise RuntimeError("Could not allocate a unique key prefix")

    now = datetime.now(timezone.utc)
    row = ApiKey(
        name=name.strip(),
        prefix=prefix,
        hash=hash_key(key),
        scopes=scopes,
        created_by=user.id,
        created_at=now,
        expires_at=now + timedelta(days=expires_in_days) if expires_in_days else None,
    )
    db.add(row)
    await db.flush()
    return row, key


def key_status(key: ApiKey, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if key.revoked_at is not None:
        return "revoked"
    if key.expires_at is not None and key.expires_at <= now:
        return "expired"
    return "active"


# ---------------------------------------------------------------------------
# Failed-attempt throttle
# ---------------------------------------------------------------------------

class FailedAttemptLimiter:
    """Refuses a client after too many bad keys in a window.

    In-process (the API runs as one uvicorn process). Keys carry ~238 bits, so this is about
    noise and log volume rather than guessing; it also stops a misconfigured client hammering
    the database.
    """

    def __init__(self, max_failures: int = 10, window_seconds: int = 300):
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = {}

    def _trim(self, client: str, now: float) -> deque[float]:
        bucket = self._failures.setdefault(client, deque())
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        return bucket

    def blocked(self, client: str) -> bool:
        bucket = self._trim(client, time.monotonic())
        if not bucket:
            self._failures.pop(client, None)
        return len(bucket) >= self.max_failures

    def record_failure(self, client: str) -> None:
        now = time.monotonic()
        self._trim(client, now).append(now)
        # Keep the map bounded if many clients fail once.
        if len(self._failures) > 10_000:
            for stale in [c for c, b in self._failures.items() if not b or now - b[-1] > self.window]:
                self._failures.pop(stale, None)

    def reset(self) -> None:
        self._failures.clear()


failed_attempts = FailedAttemptLimiter()


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class ApiKeyError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class ApiKeyPrincipal:
    """Who is calling: the key and the admin it acts for."""
    key_id: str
    name: str
    prefix: str
    scopes: list[str]
    user: User

    def allows(self, scope: str) -> bool:
        return has_scope(self.scopes, scope)


async def authenticate(db: AsyncSession, token: str, client_ip: str | None) -> ApiKeyPrincipal:
    """Check a presented key. Raises ApiKeyError (401/403/429) on any failure."""
    client = client_ip or "unknown"
    if failed_attempts.blocked(client):
        raise ApiKeyError(429, "Too many invalid API key attempts. Try again in a few minutes.")

    match = _KEY_RE.match(token or "")
    row: ApiKey | None = None
    if match:
        row = (
            await db.execute(select(ApiKey).where(ApiKey.prefix == match.group(1)))
        ).scalar_one_or_none()

    presented = hash_key(token or "")
    # Always one constant-time comparison, so a wrong prefix and a wrong secret cost the same.
    valid = hmac.compare_digest(presented, row.hash if row is not None else _DUMMY_HASH)

    if row is None or not valid:
        failed_attempts.record_failure(client)
        logger.warning("api_key.rejected reason=invalid client=%s", client)
        raise ApiKeyError(401, "Invalid API key")

    status_ = key_status(row)
    if status_ != "active":
        failed_attempts.record_failure(client)
        logger.warning("api_key.rejected reason=%s key=%s client=%s", status_, row.prefix, client)
        raise ApiKeyError(401, f"This API key has been {status_}")

    user = (await db.execute(select(User).where(User.id == row.created_by))).scalar_one_or_none()
    if user is None or not user.is_active:
        raise ApiKeyError(401, "The account that created this API key is disabled or gone")
    if user.role != "admin":
        raise ApiKeyError(403, "The account that created this API key is no longer an admin")

    now = datetime.now(timezone.utc)
    if row.last_used_at is None or now - row.last_used_at >= LAST_USED_WRITE_INTERVAL or row.last_used_ip != client_ip:
        row.last_used_at = now
        row.last_used_ip = client_ip

    return ApiKeyPrincipal(
        key_id=row.id, name=row.name, prefix=row.prefix, scopes=list(row.scopes or []), user=user,
    )


def check_request_scope(principal: ApiKeyPrincipal, method: str, path: str) -> str:
    """The scope this request uses; raises ApiKeyError(403) unless the key has it."""
    needed = required_scope(method, path)
    if needed is None or needed == SESSION_ONLY:
        logger.warning("api_key.refused reason=session-only key=%s method=%s path=%s", principal.prefix, method, path)
        raise ApiKeyError(
            403,
            "This endpoint is not available to API keys; sign in to the admin UI to use it.",
        )
    if not principal.allows(needed):
        logger.warning("api_key.refused reason=scope needed=%s key=%s method=%s path=%s", needed, principal.prefix, method, path)
        raise ApiKeyError(403, f"This API key lacks the '{needed}' scope required for {method} {path}")
    return needed


async def record_use(
    db: AsyncSession,
    principal: ApiKeyPrincipal,
    method: str,
    path: str,
    client_ip: str | None,
    user_agent: str | None,
) -> None:
    """Audit a mutating request made with a key.

    Written in its own session and committed straight away, so the record survives even when the
    request itself fails and rolls back.
    """
    from sqlalchemy.ext.asyncio import AsyncSession as _Session

    from app.models.audit_log import AuditLog

    logger.info(
        "api_key.used key=%s name=%r user=%s method=%s path=%s client=%s",
        principal.prefix, principal.name, principal.user.email, method, path, client_ip,
    )
    try:
        # Same database as the request, separate transaction.
        async with _Session(bind=db.bind, expire_on_commit=False) as session:
            session.add(AuditLog(
                user_id=principal.user.id,
                email=principal.user.email,
                action="api_key_used",
                details=f"API key '{principal.name}' (gwp_{principal.prefix}) {method} {path}",
                ip_address=client_ip,
                user_agent=user_agent,
            ))
            await session.commit()
    except Exception as e:  # never fail the request over the audit trail
        logger.warning("api_key.audit_failed key=%s error=%s", principal.prefix, e)
