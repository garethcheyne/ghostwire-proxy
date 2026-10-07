"""Checks for URLs the API itself will call (alert webhooks).

Only http(s), and by default never an internal address: loopback, private
(RFC 1918 / ULA), link-local (including cloud metadata at 169.254.169.254),
multicast, reserved or unspecified. A host name is resolved and every address
it resolves to must pass. Set `alerts_allow_internal_webhooks` to "true" to
allow internal targets (e.g. a webhook receiver on the same LAN).
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ALLOW_INTERNAL_SETTING = "alerts_allow_internal_webhooks"


class OutboundUrlError(ValueError):
    pass


def _is_internal(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"))
    )


def check_url_syntax(url: str) -> str:
    """Scheme and host checks only. Returns the host."""
    if not isinstance(url, str) or not url.strip():
        raise OutboundUrlError("A URL is required")
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in ("http", "https"):
        raise OutboundUrlError("Only http:// and https:// URLs are allowed")
    host = parts.hostname
    if not host:
        raise OutboundUrlError("The URL has no host")
    return host


async def _resolve(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(loop.getaddrinfo(host, None, type=socket.SOCK_STREAM), timeout=5)
    except (OSError, asyncio.TimeoutError):
        raise OutboundUrlError(f"Could not resolve {host}")
    return list({info[4][0] for info in infos})


async def validate_outbound_url(url: str, allow_internal: bool = False, resolver=None) -> None:
    """Raise OutboundUrlError unless `url` is an allowed outbound target."""
    host = check_url_syntax(url)
    if allow_internal:
        return
    try:
        addresses = [host] if ipaddress.ip_address(host) else []
    except ValueError:
        if host.lower() in ("localhost",) or host.lower().endswith(".localhost"):
            raise OutboundUrlError("Internal addresses are not allowed")
        addresses = await (resolver or _resolve)(host)
    for addr in addresses:
        try:
            ip = ipaddress.ip_address(addr.split("%", 1)[0])
        except ValueError:
            raise OutboundUrlError(f"Unexpected address for {host}")
        if _is_internal(ip):
            raise OutboundUrlError(
                "Internal addresses (private, loopback, link-local, metadata) are not allowed"
            )


async def internal_targets_allowed(db: AsyncSession) -> bool:
    from app.models.setting import Setting

    result = await db.execute(select(Setting.value).where(Setting.key == ALLOW_INTERNAL_SETTING))
    value = result.scalar_one_or_none()
    return (value or "").strip().lower() in ("1", "true", "yes", "on")
