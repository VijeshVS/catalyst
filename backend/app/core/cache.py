import logging
from typing import Optional
import redis.asyncio as redis
from app.core.config import settings

logger = logging.getLogger(__name__)

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
        logger.warning(f"Could not connect to Redis: {e}. Cache will operate in fallback mode.")
        redis_client = None
        return None


async def close_redis():
    global redis_client
    if redis_client:
        await redis_client.aclose()
        redis_client = None


async def get_redis() -> Optional[redis.Redis]:
    return redis_client
