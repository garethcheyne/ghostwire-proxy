"""Common utility functions for the application."""

import secrets
import string
from typing import Optional
from fastapi import Request


def get_client_ip(request: Request) -> Optional[str]:
    """The client's address.

    TrustedProxyMiddleware has already resolved it: X-Forwarded-For / X-Real-IP
    count only when the request came through a trusted proxy (TRUSTED_PROXIES),
    so a client cannot pick its own address by sending those headers.
    """
    if request.client:
        return request.client.host
    return None


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def truncate_string(s: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate a string to max_length, adding suffix if truncated."""
    if len(s) <= max_length:
        return s
    return s[:max_length - len(suffix)] + suffix
