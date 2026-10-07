"""Rate limiting configuration for API endpoints."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse


def get_client_identifier(request: Request) -> str:
    """Rate-limit key: the client address as resolved by TrustedProxyMiddleware.

    Forwarding headers only count from trusted proxies, so rotating a spoofed
    X-Forwarded-For does not give a client a fresh allowance.
    """
    return get_remote_address(request)


# Create limiter instance
limiter = Limiter(
    key_func=get_client_identifier,
    default_limits=["200/minute"],  # Default rate limit for all endpoints
    storage_uri="memory://",  # Use Redis in production: "redis://localhost:6379"
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Custom handler for rate limit exceeded errors."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please slow down your requests.",
            "retry_after": exc.detail,
        },
        # Header values must be strings: request.state.view_rate_limit is a
        # (limit, keys) tuple, and putting it here turned every 429 into a 500.
        headers={
            "Retry-After": "60",
            "X-RateLimit-Limit": str(exc.detail),
        },
    )


# Specific rate limits for different endpoint types
RATE_LIMITS = {
    "auth": "5/minute",       # Login attempts
    "api_write": "30/minute",  # Create/Update/Delete operations
    "api_read": "100/minute",  # Read operations
    "internal": "1000/minute", # Internal API calls from nginx
}
