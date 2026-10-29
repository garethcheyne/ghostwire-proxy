"""One use per TOTP code.

pyotp accepts a code for its own 30-second step and one step either side
(valid_window=1), so a code seen over someone's shoulder, or captured along with
the password, would work again for about 90 seconds. Each accepted code is
remembered in Redis for longer than that, and a second use is refused.
"""

import logging

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

# Longer than the ~90 s a code stays valid with valid_window=1.
_TTL_SECONDS = 120


async def claim_totp_code(scope: str, user_id: str, code: str) -> bool:
    """True the first time this code is used for this user and purpose; False on a replay.

    If Redis can't be reached the code is allowed (and a warning logged): sign-in
    must not depend on the replay check alone.
    """
    key = f"ghostwire:totp-used:{scope}:{user_id}:{code}"
    try:
        r = await get_redis()
        return bool(await r.set(key, "1", nx=True, ex=_TTL_SECONDS))
    except Exception:
        logger.warning("TOTP replay check unavailable (Redis); allowing the code", exc_info=True)
        return True
