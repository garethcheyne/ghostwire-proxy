"""System monitoring with Ghostwire Analytics: the settings, and the getter the telemetry reads.

The spec is ghostwire-suite/docs/analytics-reporting.md. The settings live in the `settings`
key/value table (admin only, edited on the Settings page). The ingest key is Fernet-encrypted with
ENCRYPTION_KEY and write-only: no response ever carries it, only whether one is stored.

`get_config()` is the plain, in-memory getter that app.core.ghostwire_telemetry calls from its
export threads. The values are loaded at startup, again after every save, and every minute by a
background loop (so a change made by another worker, or a restored backup, applies within a minute).
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_data, encrypt_data
from app.models.setting import Setting

logger = logging.getLogger(__name__)

KEYS = {
    "analytics_enabled": "Send monitoring to Ghostwire Analytics",
    "analytics_url": "Ghostwire Analytics URL",
    "analytics_website_id": "The Proxy's site in Ghostwire Analytics",
    "analytics_ingest_key": "The site's gwe_ ingest key (encrypted at rest)",
    "analytics_trace_sample": "Share of requests traced, 0-100",
    "analytics_browser": "Visitor analytics (page views) through /gw/",
    "analytics_replay": "Record sessions (replay and heatmaps)",
}
INGEST_KEY = "analytics_ingest_key"
REFRESH_SECONDS = 60
DEFAULT_TRACE_SAMPLE = 100

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class AnalyticsSettingsError(ValueError):
    """A value that can't be saved; the message is shown to the admin."""


def is_analytics_key(key: str) -> bool:
    return key in KEYS


# --- Stored values --------------------------------------------------------------------------------


def _bool(value: Any) -> bool:
    return str(value or "").strip().lower() in ("true", "1", "yes", "on")


def _sample(value: Any) -> int:
    try:
        return min(100, max(0, int(str(value).strip())))
    except (TypeError, ValueError):
        return DEFAULT_TRACE_SAMPLE


def _decrypt(raw: str | None) -> str:
    if not raw:
        return ""
    try:
        return decrypt_data(raw)
    except Exception:
        logger.error("The stored Ghostwire Analytics ingest key could not be decrypted (ENCRYPTION_KEY changed?)")
        return ""


async def load(db: AsyncSession) -> dict:
    """Everything stored, with the ingest key decrypted. Server side only."""
    rows = (await db.execute(select(Setting).where(Setting.key.in_(list(KEYS))))).scalars().all()
    stored = {row.key: row.value for row in rows}
    return {
        "enabled": _bool(stored.get("analytics_enabled")),
        "url": (stored.get("analytics_url") or "").strip(),
        "website_id": (stored.get("analytics_website_id") or "").strip(),
        "ingest_key": _decrypt(stored.get(INGEST_KEY)),
        "trace_sample": _sample(stored.get("analytics_trace_sample", DEFAULT_TRACE_SAMPLE)),
        "browser": _bool(stored.get("analytics_browser")),
        "replay": _bool(stored.get("analytics_replay")),
    }


def public_view(values: dict) -> dict:
    """What the settings card shows (AnalyticsSettingsValue): never the key, only whether it's set."""
    return {
        "enabled": values["enabled"],
        "url": values["url"],
        "websiteId": values["website_id"],
        "traceSample": values["trace_sample"],
        "browser": values["browser"],
        "replay": values["replay"],
        "ingestKeySet": bool(values["ingest_key"]),
    }


def active_config(values: dict) -> dict | None:
    """The live config while monitoring is on (enabled, with a URL), else None."""
    if not values.get("enabled") or not values.get("url"):
        return None
    return {
        "url": values["url"].rstrip("/"),
        "website_id": values["website_id"],
        "ingest_key": values["ingest_key"] or None,
        "trace_sample": values["trace_sample"],
        "browser": values["browser"],
        "replay": values["browser"] and values["replay"],
    }


# --- The in-memory getter -------------------------------------------------------------------------

_lock = threading.Lock()
_current: dict | None = None


def get_config() -> dict | None:
    """The current monitoring config ({url, website_id, ingest_key, trace_sample, ...}) or None while
    it's off. A plain function over memory: the telemetry calls it from its export threads."""
    with _lock:
        return dict(_current) if _current else None


def _set_current(values: dict) -> None:
    global _current
    config = active_config(values)
    with _lock:
        _current = config


async def refresh(db: AsyncSession | None = None) -> dict | None:
    """Reloads the settings into memory. Never raises (a failed read keeps the last value)."""
    try:
        if db is not None:
            _set_current(await load(db))
        else:
            from app.core.database import AsyncSessionLocal
            from app.core.ghostwire_telemetry import suppress_instrumentation

            # Reading the settings is housekeeping, not something to trace every minute.
            with suppress_instrumentation():
                async with AsyncSessionLocal() as session:
                    _set_current(await load(session))
    except Exception as error:
        logger.warning("Couldn't read the Ghostwire Analytics settings: %s", error)
    return get_config()


# --- Saving ---------------------------------------------------------------------------------------


def check_url(url: str) -> str:
    """https, or http only on this machine (localhost). Returns the URL without a trailing slash."""
    url = (url or "").strip()
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        raise AnalyticsSettingsError("The Analytics URL isn't a valid address.") from None
    if parts.scheme not in ("http", "https") or not host:
        raise AnalyticsSettingsError("The Analytics URL isn't a valid address.")
    if parts.scheme != "https" and host.lower() not in _LOCAL_HOSTS:
        raise AnalyticsSettingsError("The Analytics URL must use https://.")
    return url.rstrip("/")


def check_website_id(website_id: str) -> str:
    website_id = (website_id or "").strip()
    if not _UUID.match(website_id):
        raise AnalyticsSettingsError(
            "The website ID should be a UUID, from Analytics: Settings → the site → Tracking code."
        )
    return website_id.lower()


def check_ingest_key(key: str) -> str:
    key = (key or "").strip()
    if not key.startswith("gwe_") or len(key) > 512 or any(c.isspace() for c in key):
        raise AnalyticsSettingsError(
            "The ingest key should start with gwe_, from Analytics: Settings → the site → Errors."
        )
    return key


def check_trace_sample(value: Any) -> int:
    try:
        sample = int(value)
    except (TypeError, ValueError):
        raise AnalyticsSettingsError("Trace sampling is a whole number from 0 to 100.") from None
    if isinstance(value, bool) or sample != value or not 0 <= sample <= 100:
        raise AnalyticsSettingsError("Trace sampling is a whole number from 0 to 100.")
    return sample


async def save(db: AsyncSession, change: dict) -> dict:
    """Validates and stores an AnalyticsSettingsChange. `ingestKey`: absent keeps the stored key, ""
    removes it. Returns the public view and refreshes the in-memory config."""
    enabled = bool(change.get("enabled"))
    url = (change.get("url") or "").strip()
    website_id = (change.get("websiteId") or "").strip()
    trace_sample = check_trace_sample(change.get("traceSample", DEFAULT_TRACE_SAMPLE))
    browser = bool(change.get("browser"))
    replay = browser and bool(change.get("replay"))

    if url:
        url = check_url(url)
    if website_id:
        website_id = check_website_id(website_id)
    if enabled and not url:
        raise AnalyticsSettingsError("Enter the Analytics URL to switch monitoring on.")
    if enabled and not website_id:
        raise AnalyticsSettingsError("Enter the website ID to switch monitoring on.")

    values = {
        "analytics_enabled": "true" if enabled else "false",
        "analytics_url": url,
        "analytics_website_id": website_id,
        "analytics_trace_sample": str(trace_sample),
        "analytics_browser": "true" if browser else "false",
        "analytics_replay": "true" if replay else "false",
    }
    if "ingestKey" in change and change["ingestKey"] is not None:
        key = str(change["ingestKey"]).strip()
        values[INGEST_KEY] = encrypt_data(check_ingest_key(key)) if key else ""

    existing = {
        row.key: row for row in (await db.execute(select(Setting).where(Setting.key.in_(list(values))))).scalars()
    }
    for key, value in values.items():
        if key in existing:
            existing[key].value = value
        else:
            db.add(Setting(key=key, value=value, description=KEYS[key]))
    await db.commit()

    stored = await load(db)
    _set_current(stored)
    return public_view(stored)


# --- Test connection ------------------------------------------------------------------------------


async def check_connection(change: dict, stored_key: str = "") -> dict:
    """The same checks as the registry's testGhostwireConnection: the values are well-formed and
    <url>/api/heartbeat answers. Writes nothing, here or in Analytics."""
    try:
        url = check_url(change.get("url") or "")
        check_website_id(change.get("websiteId") or "")
        key = (change.get("ingestKey") or "").strip() or stored_key
        if key:
            check_ingest_key(key)
    except AnalyticsSettingsError as error:
        return {"ok": False, "message": str(error)}
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            response = await client.get(f"{url}/api/heartbeat")
    except httpx.HTTPError:
        return {"ok": False, "message": "Couldn't reach Analytics at that URL."}
    if response.status_code >= 300:
        return {"ok": False, "message": f"Analytics answered with HTTP {response.status_code}."}
    return {
        "ok": True,
        "message": "Analytics answered. Open the site's Realtime view in Analytics to see data arrive.",
    }
