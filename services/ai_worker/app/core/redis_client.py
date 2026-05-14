import json
import uuid
from typing import Any

import redis.asyncio as aioredis
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Redis используется для двух вещей:
# 1. Celery result backend (автоматически)
# 2. Pub/Sub — публикуем результат оценки, Assessment Service слушает
#    и пушит через WebSocket кандидату

RESULT_CHANNEL = "submission.results"


async def get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def publish_result(result: dict[str, Any]) -> None:
    """
    Публикуем результат оценки в Redis Pub/Sub канал.
    Assessment Service подписан на этот канал и при получении
    пушит данные через WebSocket кандидату.
    """
    redis = await get_redis()
    try:
        await redis.publish(RESULT_CHANNEL, json.dumps(result, default=str))
        logger.info("Result published to Redis", submission_id=result.get("submission_id"))
    finally:
        await redis.aclose()
