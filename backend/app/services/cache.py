"""Best-effort Redis JSON cache for hot dashboard endpoints.

Offline-first rule: the dashboard must work with zero external dependencies
beyond PostgreSQL — so every Redis failure degrades silently to a direct DB
read. Never raise out of this module.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

import redis.asyncio as aioredis

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_redis() -> aioredis.Redis:
    return aioredis.from_url(
        get_settings().redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


async def cached_json(
    key: str, producer: Callable[[], Awaitable[Any]], ttl_seconds: int | None = None
) -> Any:
    """Return the cached JSON value for `key`, or produce, cache, and return it."""
    ttl = ttl_seconds if ttl_seconds is not None else get_settings().dashboard_cache_ttl_seconds
    try:
        hit = await get_redis().get(key)
        if hit is not None:
            return json.loads(hit)
    except Exception:
        logger.debug("redis get failed for %s — falling through to DB", key, exc_info=True)

    value = await producer()
    try:
        await get_redis().set(key, json.dumps(value, ensure_ascii=False, default=str), ex=ttl)
    except Exception:
        logger.debug("redis set failed for %s — serving uncached", key, exc_info=True)
    return value
