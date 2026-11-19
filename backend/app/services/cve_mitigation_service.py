"""CVE mitigations: named, reversible switches the upgrade script turns on while a CVE in cve/ is open.

Each one is a setting (cve_mitigation_<name>) that config generation honours, so turning it on or off is
one write plus the usual generate, `nginx -t`, reload (or roll back) of validate_and_apply. Nothing per
host changes: hosts keep their own settings and get them back when the mitigation is turned off.

The upgrade script sets them through /api/internal/cve/mitigations (cve/README.md); the generic
/api/settings/{key} routes refuse the keys, as a write there wouldn't regenerate the config.
"""

import json
import logging
import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.setting import Setting

logger = logging.getLogger(__name__)

SETTING_PREFIX = "cve_mitigation_"

# name → what it does. Each must be honoured by openresty_service and listed in CVE_MITIGATIONS in
# upgradeGhostwireProxy.sh; an advisory in cve/ names one in its "mitigations".
MITIGATIONS: dict[str, str] = {
    "disable_http2": "Leave `http2 on;` out of every server block, so HTTPS is served over HTTP/1.1",
}

CVE_ID_RE = re.compile(r"^(CVE-\d{4}-\d{4,}|GHSA(-[a-z0-9]{4}){3})$")


def setting_key(name: str) -> str:
    return SETTING_PREFIX + name


def is_mitigation_key(key: str) -> bool:
    return key.startswith(SETTING_PREFIX)


async def active_mitigations(db: AsyncSession) -> set[str]:
    """The mitigations that are on, read in the caller's session (so a flushed change counts)."""
    result = await db.execute(select(Setting).where(Setting.key.in_([setting_key(n) for n in MITIGATIONS])))
    return {s.key.removeprefix(SETTING_PREFIX) for s in result.scalars() if (s.value or "").lower() == "true"}


async def set_mitigation(
    db: AsyncSession,
    name: str,
    active: bool,
    cves: list[str] | None = None,
    *,
    source: str = "upgrade script",
    user_id: str | None = None,
    ip_address: str | None = None,
) -> tuple[bool, str]:
    """Turn a mitigation on or off and apply it to nginx. Nothing is saved unless nginx takes it."""
    if name not in MITIGATIONS:
        raise ValueError(f"Unknown mitigation {name!r}")
    cves = [c for c in (cves or []) if CVE_ID_RE.match(c)]

    key = setting_key(name)
    setting = (await db.execute(select(Setting).where(Setting.key == key))).scalar_one_or_none()
    if setting is None:
        setting = Setting(key=key)
        db.add(setting)
    was_active = (setting.value or "").lower() == "true"
    setting.value = "true" if active else "false"
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    if active:
        setting.description = f"On since {when} for {', '.join(cves) or 'a CVE'} ({source}). {MITIGATIONS[name]}."
    else:
        setting.description = f"Off since {when} ({source}). {MITIGATIONS[name]}."
    db.add(
        AuditLog(
            action="cve_mitigation_on" if active else "cve_mitigation_off",
            user_id=user_id,
            ip_address=ip_address,
            details=json.dumps({"mitigation": name, "cves": cves, "source": source, "was_active": was_active}),
        )
    )

    # Late import: the apply sequence lives with the proxy host routes, which import this module's
    # neighbours at load time.
    from app.api.routes.proxy_hosts import validate_and_apply

    ok, message = await validate_and_apply(db)
    if ok:
        logger.warning(f"CVE mitigation {name} turned {'on' if active else 'off'} ({source}; {', '.join(cves)})")
    else:
        logger.error(f"CVE mitigation {name} could not be turned {'on' if active else 'off'}: {message}")
    return ok, message
