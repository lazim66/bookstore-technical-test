"""Redis connection utilities."""

import logging

from redis.asyncio import Redis
from src.settings import settings

logger = logging.getLogger(__name__)


def get_redis_client() -> Redis:
    return Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        decode_responses=True,
    )


redis_client = get_redis_client()
