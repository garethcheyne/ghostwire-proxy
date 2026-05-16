"""
Short-lived JSON response cache backed by Redis.

Used to absorb dashboard / analytics traffic where the same heavy
aggregate query is fired repeatedly within seconds. Cache misses fall
back to the underlying computation; cache failures are swallowed so a
broken Redis never takes down the API.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Awaitable, Callable

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "ghostwire:cache:"


def _default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    # Pydantic v2 models
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def cache_get(key: str) -> Any | None:
    try:
        client = await get_redis()
        raw = await client.get(_CACHE_PREFIX + key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as e:  # noqa: BLE001 - cache must never break a request
        logger.debug("cache_get failed for %s: %s", key, e)
        return None


async def cache_set(key: str, value: Any, ttl: int = 30) -> None:
    try:
        client = await get_redis()
        await client.set(
            _CACHE_PREFIX + key,
            json.dumps(value, default=_default),
            ex=ttl,
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("cache_set failed for %s: %s", key, e)


async def cache_delete(*keys: str) -> None:
    if not keys:
        return
    try:
        client = await get_redis()
        await client.delete(*[_CACHE_PREFIX + k for k in keys])
    except Exception as e:  # noqa: BLE001
        logger.debug("cache_delete failed: %s", e)


async def cache_delete_prefix(prefix: str) -> None:
    """Delete all cache entries whose key starts with ``prefix``."""
    try:
        client = await get_redis()
        full = _CACHE_PREFIX + prefix
        # SCAN is non-blocking; safe to use on a hot Redis instance.
        cursor = 0
        while True:
            cursor, batch = await client.scan(cursor=cursor, match=full + "*", count=200)
            if batch:
                await client.delete(*batch)
            if cursor == 0:
                break
    except Exception as e:  # noqa: BLE001
        logger.debug("cache_delete_prefix(%s) failed: %s", prefix, e)


async def cached_json(
    key: str,
    ttl: int,
    producer: Callable[[], Awaitable[Any]],
) -> Any:
    """
    Return cached JSON-serialisable value for ``key``, calling ``producer``
    on miss. ``producer`` should return a JSON-serialisable structure or a
    Pydantic model (model_dump is used automatically).
    """
    hit = await cache_get(key)
    if hit is not None:
        return hit
    value = await producer()
    # Normalise pydantic models so subsequent reads come back as plain dicts.
    if hasattr(value, "model_dump"):
        payload = value.model_dump()
    elif hasattr(value, "dict"):
        payload = value.dict()
    else:
        payload = value
    await cache_set(key, payload, ttl=ttl)
    return payload
