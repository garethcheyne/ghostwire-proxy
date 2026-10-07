"""Where the auth portal may send a visitor after sign-in.

Only back to the protected site itself: a relative path ("/admin?x=1"), or an
absolute http(s) URL on the host the request came in on. Anything else
(another site, a scheme-relative "//evil", "javascript:", backslash tricks,
control characters) becomes "/".
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlsplit

from fastapi import Request

_CONTROL = re.compile(r"[\x00-\x1f\x7f\\]")


def _host_only(value: Optional[str]) -> str:
    value = (value or "").strip().lower()
    if value.startswith("["):
        return value.split("]", 1)[0] + "]"
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def request_host(request: Request) -> str:
    return request.headers.get("host") or ""


def request_origin(request: Request) -> str:
    scheme = request.url.scheme if request.url.scheme in ("http", "https") else "https"
    return f"{scheme}://{request_host(request)}"


def is_safe_redirect(target: Optional[str], host: str) -> bool:
    if not target or _CONTROL.search(target) or target != target.strip():
        return False
    if target.startswith("/"):
        # "//evil.example" and "/\evil.example" are other sites to a browser
        return not target.startswith("//")
    parts = urlsplit(target)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return False
    if parts.username or parts.password:
        return False
    return bool(host) and _host_only(parts.netloc) == _host_only(host)


def safe_redirect_target(target: Optional[str], request: Request) -> str:
    return target if is_safe_redirect(target, request_host(request)) else "/"
