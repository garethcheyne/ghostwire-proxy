"""Which address a request really came from.

X-Forwarded-For, X-Real-IP and X-Forwarded-Proto are only believed when the
TCP peer is a trusted proxy: by default the OpenResty container and the admin
UI container (resolved by name on the Docker network) and loopback. Anyone
else, for example a client reaching the published API port directly, is
identified by its socket address, whatever headers it sends.

Configure with TRUSTED_PROXIES: a comma-separated list of IPs, CIDRs and/or
host names (names are re-resolved every minute).
"""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
import threading
import time
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

DEFAULT_TRUSTED_PROXIES = "127.0.0.1,::1,ghostwire-proxy-nginx,ghostwire-proxy-ui"
_REFRESH_SECONDS = 60

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


def _parse_ip(value: Optional[str]):
    if not value:
        return None
    value = value.strip().strip('"')
    # "[2001:db8::1]:443" / "203.0.113.5:1234" (some proxies include a port)
    if value.startswith("["):
        value = value[1:].split("]", 1)[0]
    elif value.count(":") == 1:
        value = value.split(":", 1)[0]
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


class TrustedProxies:
    """A list of trusted proxy networks, with host names resolved lazily."""

    def __init__(self, spec: Optional[str] = None, resolver=None):
        self.spec = spec if spec is not None else (os.environ.get("TRUSTED_PROXIES") or DEFAULT_TRUSTED_PROXIES)
        self._resolver = resolver or self._resolve
        self._static: list[IPNetwork] = []
        self._names: list[str] = []
        for item in (part.strip() for part in self.spec.split(",")):
            if not item:
                continue
            try:
                self._static.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                self._names.append(item)
        self._resolved: list[IPNetwork] = []
        self._resolved_at = 0.0
        self._lock = threading.Lock()

    @staticmethod
    def _resolve(name: str) -> list[str]:
        try:
            return list({info[4][0] for info in socket.getaddrinfo(name, None)})
        except OSError:
            return []

    def _networks(self) -> list[IPNetwork]:
        if self._names and time.monotonic() - self._resolved_at > _REFRESH_SECONDS:
            with self._lock:
                if time.monotonic() - self._resolved_at > _REFRESH_SECONDS:
                    resolved: list[IPNetwork] = []
                    for name in self._names:
                        for addr in self._resolver(name):
                            try:
                                resolved.append(ipaddress.ip_network(addr))
                            except ValueError:
                                continue
                    self._resolved = resolved
                    self._resolved_at = time.monotonic()
        return self._static + self._resolved

    def is_trusted(self, ip) -> bool:
        if ip is None:
            return False
        return any(ip.version == net.version and ip in net for net in self._networks())

    def client_ip(
        self,
        peer: Optional[str],
        forwarded_for: Optional[str] = None,
        real_ip: Optional[str] = None,
    ) -> Optional[str]:
        """The client address for a request from `peer` carrying these headers.

        From an untrusted peer: the peer. From a trusted one: walk
        X-Forwarded-For from the right (each proxy appends the address it saw)
        and take the first untrusted hop; with no X-Forwarded-For, X-Real-IP.
        """
        peer_ip = _parse_ip(peer)
        if peer_ip is None:
            return peer
        if not self.is_trusted(peer_ip):
            return str(peer_ip)

        hops = [h for h in (forwarded_for or "").split(",") if h.strip()]
        if hops:
            last = None
            for raw in reversed(hops):
                ip = _parse_ip(raw)
                if ip is None:
                    # Garbage in the chain: don't look further left than this.
                    break
                last = ip
                if not self.is_trusted(ip):
                    return str(ip)
            return str(last) if last is not None else str(peer_ip)

        real = _parse_ip(real_ip)
        if real is not None:
            return str(real)
        return str(peer_ip)


_trusted: Optional[TrustedProxies] = None


def trusted_proxies() -> TrustedProxies:
    global _trusted
    if _trusted is None:
        _trusted = TrustedProxies()
    return _trusted


def reset_trusted_proxies(spec: Optional[str] = None) -> TrustedProxies:
    """Re-read TRUSTED_PROXIES (tests)."""
    global _trusted
    _trusted = TrustedProxies(spec)
    return _trusted


def _header(headers: Iterable[tuple[bytes, bytes]], name: bytes) -> Optional[str]:
    values = [v.decode("latin-1") for k, v in headers if k.lower() == name]
    return ",".join(values) if values else None


class TrustedProxyMiddleware:
    """ASGI middleware: set the request's client address and scheme.

    Replaces uvicorn's --proxy-headers (which, with --forwarded-allow-ips '*',
    believed X-Forwarded-For from anyone). request.client.host is then the
    real client for every route, rate limiter and audit log.
    """

    def __init__(self, app, proxies: Optional[TrustedProxies] = None):
        self.app = app
        self._proxies = proxies

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            proxies = self._proxies or trusted_proxies()
            client = scope.get("client")
            peer = client[0] if client else None
            peer_ip = _parse_ip(peer)
            if peer_ip is not None and proxies.is_trusted(peer_ip):
                headers = scope.get("headers") or []
                ip = proxies.client_ip(
                    peer,
                    _header(headers, b"x-forwarded-for"),
                    _header(headers, b"x-real-ip"),
                )
                scope = dict(scope)
                scope["client"] = (ip, client[1] if client else 0)
                proto = (_header(headers, b"x-forwarded-proto") or "").split(",")[0].strip().lower()
                if proto in ("http", "https"):
                    scope["scheme"] = ("wss" if proto == "https" else "ws") if scope["type"] == "websocket" else proto
        await self.app(scope, receive, send)
