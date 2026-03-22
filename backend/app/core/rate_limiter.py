"""Rate limiting configuration for API endpoints."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request
from fastapi.responses import JSONResponse


def get_client_identifier(request: Request) -> str:
    """
    Get client identifier for rate limiting.

    Uses X-Forwarded-For header if available (for reverse proxy setups),
    otherwise falls back to direct client IP.
    """
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
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
        headers={
            "Retry-After": str(exc.detail),
            "X-RateLimit-Limit": request.state.view_rate_limit if hasattr(request.state, "view_rate_limit") else "unknown",
        },
    )


# Specific rate limits for different endpoint types
RATE_LIMITS = {
    "auth": "5/minute",       # Login attempts
    "api_write": "30/minute",  # Create/Update/Delete operations
    "api_read": "100/minute",  # Read operations
    "internal": "1000/minute", # Internal API calls from nginx
}
