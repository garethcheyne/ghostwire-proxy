"""
Upstream health monitoring for proxy hosts.

Answers "is this virtual host actually up?" by connecting to the host's own
upstream rather than going back through nginx, so the result isn't muddied by
DNS, certificates, or the proxy layer itself.

State lives on the ProxyHost row rather than in memory, so a restart doesn't
re-announce outages that were already reported.

A load-balanced host (one with enabled upstream servers) is checked server by
server: each one's status, latency and last error land on its UpstreamServer
row, and the host counts as up while any server that isn't in maintenance
answers. Probes only ever contact the configured host:port of each server,
never follow redirects and ignore proxy environment variables, so the probe
path can't be used to reach anything else.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.proxy_host import ProxyHost, UpstreamServer
from app.services.load_balancing import format_server_address

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
# Same, per upstream server id.
_server_failures: dict[str, int] = {}


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


async def probe_server(
    scheme: str,
    host: str,
    port: int,
    check_type: str = "http",
    path: str = "/",
    timeout: float = CHECK_TIMEOUT,
) -> tuple[bool, Optional[str], Optional[int]]:
    """Probe one upstream server. Returns (is_up, error, latency_ms).

    tcp: the port accepts a connection. http: GET `path` answers with any
    status below 500 (a 5xx means the process is up but failing, which is
    exactly when it should leave the rotation).
    """
    started = time.monotonic()
    try:
        if check_type == "tcp":
            _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True, None, int((time.monotonic() - started) * 1000)

        raw_path, _, query = (path or "/").partition("?")
        # Built from parts, so nothing in the path can change the host or port.
        parts = {"scheme": scheme, "host": host, "port": port, "path": raw_path or "/"}
        if query:
            parts["query"] = query.encode()
        url = httpx.URL(**parts)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            verify=False,  # internal upstreams routinely use self-signed certs
            trust_env=False,  # never route a probe through an env-configured proxy
        ) as client:
            async with client.stream("GET", url, headers={"User-Agent": "Ghostwire-HealthCheck"}) as response:
                code = response.status_code
        latency = int((time.monotonic() - started) * 1000)
        if code >= 500:
            return False, f"HTTP {code}", latency
        return True, None, latency
    except (asyncio.TimeoutError, httpx.TimeoutException):
        return False, f"timed out after {timeout:g}s", None
    except httpx.HTTPError as e:
        return False, str(e)[:300] or type(e).__name__, None
    except OSError as e:
        return False, (e.strerror or str(e))[:300], None
    except Exception as e:  # pragma: no cover - defensive
        return False, f"{type(e).__name__}: {e}"[:300], None


def _probe_args(host: ProxyHost, server: UpstreamServer) -> dict:
    timeout = getattr(host, "health_check_timeout", None) or CHECK_TIMEOUT
    return {
        "scheme": host.forward_scheme or "http",
        "host": server.host,
        "port": server.port,
        "check_type": getattr(host, "health_check_type", None) or "http",
        "path": getattr(host, "health_check_path", None) or "/",
        "timeout": float(timeout),
    }


def _apply_server_result(server: UpstreamServer, is_up: bool, error: Optional[str],
                         latency: Optional[int], now: datetime, debounce: bool = True) -> None:
    previous = server.last_status or "unknown"
    if is_up:
        _server_failures.pop(server.id, None)
        server.last_status = "up"
    else:
        failures = _server_failures.get(server.id, 0) + 1
        _server_failures[server.id] = failures
        if not debounce or failures >= FAILURES_BEFORE_DOWN or previous == "unknown":
            server.last_status = "down"
    server.last_error = None if is_up else error
    server.last_latency_ms = latency
    server.last_check_at = now


def _update_auto_down(host: ProxyHost, servers: list[UpstreamServer]) -> bool:
    """Take confirmed-down servers out of rotation (and put recovered ones back).

    Only when the host opted in. Never leaves the group with nothing to send
    traffic to: if every server is down, nginx's own retries are the better bet.
    Returns True when the rendered config changes.
    """
    changed = False
    if not getattr(host, "lb_auto_down", False):
        for server in servers:
            if server.auto_down:
                server.auto_down = False  # not rendered while the option is off
        return False
    for server in servers:
        if server.auto_down and server.last_status == "up":
            server.auto_down = False
            changed = True
    for server in servers:
        if server.last_status == "down" and not server.auto_down and not server.down:
            others = [s for s in servers if s is not server and not s.down and not s.auto_down]
            if not others:
                continue
            server.auto_down = True
            changed = True
    return changed


async def _check_servers(host: ProxyHost, servers: list[UpstreamServer],
                         semaphore: asyncio.Semaphore) -> tuple[bool, Optional[str], str]:
    async def one(server):
        async with semaphore:
            return await probe_server(**_probe_args(host, server))

    results = await asyncio.gather(*(one(s) for s in servers))
    now = datetime.now(timezone.utc)
    answering = 0
    first_error = None
    for server, (ok, error, latency) in zip(servers, results):
        _apply_server_result(server, ok, error, latency, now)
        # A server in maintenance doesn't take traffic, so it can't keep the host up.
        if ok and not server.down:
            answering += 1
        elif not ok and first_error is None:
            first_error = f"{format_server_address(server.host, server.port)}: {error}"

    upstream = f"{len(servers)} backends" if len(servers) != 1 else format_server_address(servers[0].host, servers[0].port)
    if answering:
        return True, None, upstream
    return False, f"no backend answering ({first_error})" if first_error else "every backend is in maintenance", upstream


async def check_upstream_servers_now(db: AsyncSession, host: ProxyHost) -> list[dict]:
    """On-demand probe of a host's enabled servers (the editor's "Check now").

    Writes the raw result without debouncing and without notifications; the
    background loop stays the only thing that alerts.
    """
    servers = [s for s in host.upstream_servers if s.enabled]
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)

    async def one(server):
        async with semaphore:
            return await probe_server(**_probe_args(host, server))

    results = await asyncio.gather(*(one(s) for s in servers))
    now = datetime.now(timezone.utc)
    out = []
    for server, (ok, error, latency) in zip(servers, results):
        _apply_server_result(server, ok, error, latency, now, debounce=False)
        out.append({
            "id": server.id, "host": server.host, "port": server.port,
            "status": server.last_status, "latency_ms": latency, "error": server.last_error,
        })
    await db.commit()
    return out


async def _check_one(host: ProxyHost, semaphore: asyncio.Semaphore) -> dict:
    servers = [s for s in (host.upstream_servers or []) if s.enabled]
    config_changed = False
    if servers:
        is_up, error, upstream = await _check_servers(host, servers, semaphore)
        config_changed = _update_auto_down(host, servers)
    else:
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
        "config_changed": config_changed,
    }


async def run_health_checks(db: AsyncSession) -> dict:
    """Probe every enabled, monitored host and notify on state changes."""
    result = await db.execute(
        select(ProxyHost)
        .options(selectinload(ProxyHost.upstream_servers))
        .where(
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

    # Auto-down moved a server in or out of rotation: re-render and reload
    # through the same nginx -t gate an admin's edit goes through.
    if any(isinstance(o, dict) and o.get("config_changed") for o in outcomes):
        try:
            from app.api.routes.proxy_hosts import validate_and_apply
            ok, msg = await validate_and_apply(db)
            if not ok:
                logger.error(f"Auto-down config change was not applied: {msg}")
        except Exception as e:
            logger.error(f"Auto-down config change failed: {e}")

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
