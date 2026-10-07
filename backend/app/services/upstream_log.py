"""
Which backend served a request: parsing nginx's $upstream_* variables.

For a load-balanced host nginx may try several servers for one request
(proxy_next_upstream). Its variables then hold one entry per attempt, in order:

    $upstream_addr           10.0.0.5:8050, 10.0.0.5:8051
    $upstream_status         502, 200
    $upstream_response_time  0.004, 0.120

", " separates servers tried within one upstream group; " : " separates groups
when an internal redirect (X-Accel-Redirect, error_page) moved the request on.
The last entry is the one that produced the response. An attempt that never
reached a server shows "-" for its status/time, and when no server was
available at all the address is the upstream's name instead of host:port.
"""
from __future__ import annotations

import asyncio
import ipaddress
import re
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional

_SPLIT = re.compile(r"\s*,\s*|\s+:\s+")

# Column sizes in traffic_logs
ADDR_MAX = 255
ATTEMPTS_MAX = 10


@dataclass
class UpstreamAttempt:
    addr: str
    status: Optional[int] = None
    time_ms: Optional[int] = None

    def as_dict(self) -> dict:
        return {"addr": self.addr, "status": self.status, "ms": self.time_ms}


@dataclass
class UpstreamResult:
    attempts: list[UpstreamAttempt] = field(default_factory=list)

    @property
    def final(self) -> Optional[UpstreamAttempt]:
        return self.attempts[-1] if self.attempts else None

    @property
    def final_addr(self) -> Optional[str]:
        return self.final.addr if self.final else None

    @property
    def final_time_ms(self) -> Optional[int]:
        return self.final.time_ms if self.final else None

    @property
    def count(self) -> int:
        return len(self.attempts)

    @property
    def failover(self) -> bool:
        """True when more than one server was tried for this request."""
        return len(self.attempts) > 1


def _split(value: Optional[str]) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in _SPLIT.split(value.strip()) if part.strip()]


def _int(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ms(value: str) -> Optional[int]:
    try:
        return int(round(float(value) * 1000))
    except (TypeError, ValueError):
        return None


def parse_upstream(addr: Optional[str], status: Optional[str] = None,
                   response_time: Optional[str] = None) -> UpstreamResult:
    """Pair up nginx's per-attempt lists. Missing or short lists give None values."""
    addrs = _split(addr)
    statuses = _split(status)
    times = _split(response_time)
    attempts = []
    for i, a in enumerate(addrs):
        attempts.append(UpstreamAttempt(
            addr=a,
            status=_int(statuses[i]) if i < len(statuses) else None,
            time_ms=_ms(times[i]) if i < len(times) else None,
        ))
    if not attempts and times:
        # Response time without an address (shouldn't happen, but keep the timing)
        attempts.append(UpstreamAttempt(addr="", time_ms=_ms(times[-1])))
    return UpstreamResult(attempts=attempts[-ATTEMPTS_MAX:])


def split_host_port(addr: str) -> tuple[str, Optional[int]]:
    """'10.0.0.5:8050' -> ('10.0.0.5', 8050); '[fd00::5]:80' -> ('fd00::5', 80)."""
    if addr.startswith("["):
        host, _, rest = addr[1:].partition("]")
        return host.lower(), _int(rest.lstrip(":"))
    host, sep, port = addr.rpartition(":")
    if not sep:
        return addr.lower(), None
    return host.lower(), _int(port)


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


# hostname -> (expires_at, {ips})
_dns_cache: dict[str, tuple[float, set[str]]] = {}
_DNS_TTL = 300.0


async def _resolve(hostname: str) -> set[str]:
    now = time.monotonic()
    cached = _dns_cache.get(hostname)
    if cached and cached[0] > now:
        return cached[1]
    ips: set[str] = set()
    try:
        infos = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(hostname, None), 2.0)
        ips = {str(ipaddress.ip_address(info[4][0])) for info in infos}
    except Exception:
        pass
    _dns_cache[hostname] = (now + _DNS_TTL, ips)
    return ips


async def match_upstream_server(final_addr: Optional[str], servers: Iterable) -> Optional[str]:
    """The id of the UpstreamServer row that answered, or None.

    nginx reports resolved addresses, so a server configured by hostname is
    matched by resolving it (cached for five minutes).
    """
    if not final_addr:
        return None
    host, port = split_host_port(final_addr)
    if port is None:
        return None  # e.g. the upstream's name when no server was available
    try:
        host = str(ipaddress.ip_address(host))
    except ValueError:
        pass
    candidates = [s for s in servers if s.port == port]
    for s in candidates:
        if str(s.host).lower() == host:
            return s.id
    for s in candidates:
        if not _is_ip(str(s.host)) and host in await _resolve(str(s.host)):
            return s.id
    return None
