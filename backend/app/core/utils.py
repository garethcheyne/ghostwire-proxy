"""Common utility functions for the application."""

import secrets
import string
from typing import Optional
from fastapi import Request


def get_client_ip(request: Request) -> Optional[str]:
    """
    Extract client IP address from request headers.

    Handles X-Forwarded-For header for reverse proxy setups.
    Returns the first IP in the chain (original client IP).
    """
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs: client, proxy1, proxy2, ...
        # The first one is the original client IP
        return forwarded_for.split(",")[0].strip()

    # Fallback to direct client IP
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
