"""
Upstream health monitoring for proxy hosts.

Answers "is this virtual host actually up?" by connecting to the host's own
upstream rather than going back through nginx, so the result isn't muddied by
DNS, certificates, or the proxy layer itself.

State lives on the ProxyHost row rather than in memory, so a restart doesn't
re-announce outages that were already reported.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.proxy_host import ProxyHost

logger = logging.getLogger(__name__)

CHECK_TIMEOUT = 5.0
# One dropped probe shouldn't page anyone; require two in a row before a host
# is called down.
FAILURES_BEFORE_DOWN = 2
# Upstreams are checked concurrently, but not unboundedly.
MAX_CONCURRENT_CHECKS = 10

# host_id -> consecutive failure count. Only used to debounce within a run of
# checks; the authoritative state is the persisted health_status column.
_consecutive_failures: dict[str, int] = {}


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
    return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"


async def probe_upstream(host: ProxyHost) -> tuple[bool, Optional[str]]:
    """Probe a host's upstream. Returns (is_up, error_message)."""
    url = f"{host.forward_scheme}://{host.forward_host}:{host.forward_port}/"
    try:
        async with httpx.AsyncClient(
            timeout=CHECK_TIMEOUT,
            follow_redirects=False,
            # Internal upstreams routinely use self-signed certs; this probe is
            # about reachability, not certificate validation.
            verify=False,
        ) as client:
            await client.get(url)
        # Any HTTP response means the upstream is listening and answering. A 401
        # or 404 on "/" is a normal backend, not an outage — only a transport
        # failure counts as down.
        return True, None
    except httpx.TimeoutException:
        return False, f"timed out after {CHECK_TIMEOUT:g}s"
    except httpx.HTTPError as e:
        return False, str(e)[:300] or type(e).__name__
    except Exception as e:  # pragma: no cover - defensive
        return False, f"{type(e).__name__}: {e}"[:300]


async def _check_one(host: ProxyHost, semaphore: asyncio.Semaphore) -> dict:
    async with semaphore:
        is_up, error = await probe_upstream(host)

    upstream = f"{host.forward_host}:{host.forward_port}"
    previous = host.health_status or "unknown"
    now = datetime.now(timezone.utc)

    if is_up:
        _consecutive_failures.pop(host.id, None)
        new_status = "up"
    else:
        failures = _consecutive_failures.get(host.id, 0) + 1
        _consecutive_failures[host.id] = failures
        # Hold the previous status until the failure is confirmed.
        new_status = "down" if failures >= FAILURES_BEFORE_DOWN else previous

    transition = None
    if new_status != previous:
        if new_status == "down":
            transition = "down"
        elif new_status == "up" and previous == "down":
            transition = "recovered"

    downtime = None
    if transition == "recovered" and host.health_checked_at:
        last = host.health_checked_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        downtime = _format_duration((now - last).total_seconds())

    host.health_status = new_status
    host.health_error = None if is_up else error
    # Only advance the timestamp while the status is steady, so a recovery can
    # report how long the outage lasted.
    if transition != "recovered":
        host.health_checked_at = now

    return {
        "host": host,
        "transition": transition,
        "upstream": upstream,
        "error": error,
        "downtime": downtime,
    }


async def run_health_checks(db: AsyncSession) -> dict:
    """Probe every enabled, monitored host and notify on state changes."""
    result = await db.execute(
        select(ProxyHost).where(
            (ProxyHost.enabled == True) & (ProxyHost.health_check_enabled == True)  # noqa: E712
        )
    )
    hosts = list(result.scalars().all())
    if not hosts:
        return {"checked": 0, "down": 0, "recovered": 0}

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)
    outcomes = await asyncio.gather(
        *(_check_one(host, semaphore) for host in hosts),
        return_exceptions=True,
    )

    changes = [o for o in outcomes if isinstance(o, dict) and o["transition"]]

    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            logger.error(f"Health check raised: {outcome}")

    await db.commit()

    # Notifications go out only after the new state is committed, so a failure
    # to send can never leave the DB claiming something was already announced.
    from app.services.push_service import push_service
    from app.services.alert_service import dispatch_alert

    down = recovered = 0
    for change in changes:
        host = change["host"]
        domain = host.domain_names[0] if host.domain_names else host.id
        try:
            if change["transition"] == "down":
                down += 1
                logger.warning(f"Host down: {domain} -> {change['upstream']} ({change['error']})")
                await push_service.notify_host_down(
                    domain=domain,
                    upstream=change["upstream"],
                    error=change["error"],
                    host_id=host.id,
                    db=db,
                )
                # Push already went out above with its own actions/urgency; this
                # fans the same alert out to webhook/Slack/Telegram/email.
                await dispatch_alert(
                    db=db,
                    alert_type="host_down",
                    severity="critical",
                    title=f"Host Down - {domain}",
                    message=f"{change['upstream']} is not responding ({change['error']})",
                    data={"domain": domain, "upstream": change["upstream"], "host_id": host.id},
                    skip_push=True,
                )
            else:
                recovered += 1
                logger.info(f"Host recovered: {domain} -> {change['upstream']}")
                await push_service.notify_host_recovered(
                    domain=domain,
                    upstream=change["upstream"],
                    downtime=change["downtime"],
                    host_id=host.id,
                    db=db,
                )
                await dispatch_alert(
                    db=db,
                    alert_type="host_recovered",
                    severity="medium",
                    title=f"Host Recovered - {domain}",
                    message=f"{change['upstream']} is responding again",
                    data={"domain": domain, "upstream": change["upstream"], "host_id": host.id},
                    skip_push=True,
                )
        except Exception as e:
            logger.error(f"Failed to send health notification for {domain}: {e}")

    return {"checked": len(hosts), "down": down, "recovered": recovered}
