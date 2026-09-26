"""
Redis connection lifecycle plus the small JSON cache the API reads through.

Every helper here is failure tolerant on purpose. A cache outage must degrade
the API to "always query PostgreSQL", never turn into a 500, so Redis errors are
logged and reported as a miss. :func:`get_redis` returning ``None`` (Redis was
never reachable) is handled the same way as a command that failed.
"""

import json
import logging
from typing import Any, Iterable, Optional

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

#: Every key this app writes is namespaced, so a shared Redis instance stays
#: legible (and flushable) from the outside.
KEY_PREFIX = "catalyst"

redis_client: Optional[redis.Redis] = None


async def init_redis() -> Optional[redis.Redis]:
    global redis_client
    try:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
        )
        await redis_client.ping()
        logger.info("Connected to Redis successfully.")
        return redis_client
    except Exception as e:
        logger.warning(f"Could not connect to Redis: {e}. Serving from PostgreSQL instead.")
        redis_client = None
        return None


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.aclose()
        redis_client = None


async def get_redis() -> Optional[redis.Redis]:
    return redis_client


def snapshot_key(project_id: str, env: str) -> str:
    """Cache key holding the serialized flag snapshot of one project environment."""
    return f"{KEY_PREFIX}:snapshot:{project_id}:{env}"


async def cache_get_json(key: str) -> Optional[Any]:
    """Reads and decodes a JSON value, or ``None`` on a miss or any Redis error."""
    client = await get_redis()
    if client is None:
        return None
    try:
        raw = await client.get(key)
    except Exception as e:  # noqa: BLE001 - a cache read must never raise
        logger.warning("cache read failed for %s: %s", key, e)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        # A truncated or foreign value is treated as a miss and will be overwritten.
        logger.warning("discarding undecodable cache entry %s", key)
        return None


async def cache_set_json(key: str, value: Any, ttl: Optional[int] = None) -> bool:
    """Writes a JSON value. Returns whether it was stored."""
    client = await get_redis()
    if client is None:
        return False
    try:
        payload = json.dumps(value, separators=(",", ":"), default=str)
    except (TypeError, ValueError) as e:
        logger.warning("could not serialize cache entry %s: %s", key, e)
        return False
    try:
        if ttl and ttl > 0:
            await client.set(key, payload, ex=ttl)
        else:
            await client.set(key, payload)
    except Exception as e:  # noqa: BLE001 - a cache write must never raise
        logger.warning("cache write failed for %s: %s", key, e)
        return False
    return True


async def cache_delete(keys: Iterable[str]) -> int:
    """Deletes keys, ignoring an empty list and any Redis error."""
    targets = [key for key in keys if key]
    if not targets:
        return 0
    client = await get_redis()
    if client is None:
        return 0
    try:
        return int(await client.delete(*targets))
    except Exception as e:  # noqa: BLE001 - invalidation is best effort
        logger.warning("cache delete failed for %s: %s", targets, e)
        return 0
