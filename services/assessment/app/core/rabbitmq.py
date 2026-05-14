import json
import uuid
from typing import Any

import aio_pika
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class RabbitMQPublisher:
    """
    Публикует задачи оценки в RabbitMQ.
    Assessment Service — producer, AI Worker — consumer.

    Паттерн: после создания Submission в БД сразу публикуем
    сообщение в очередь. AI Worker подберёт и оценит асинхронно.
    Это позволяет HTTP-запросу вернуть ответ мгновенно,
    не ожидая 10-30 секунд работы AI.
    """

    def __init__(self) -> None:
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.Channel | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        self._channel = await self._connection.channel()

        # Объявляем очереди — idempotent операция (создаст если нет)
        await self._channel.declare_queue(
            settings.evaluation_queue,
            durable=True,   # очередь переживёт перезапуск RabbitMQ
        )
        await self._channel.declare_queue(
            settings.feedback_queue,
            durable=True,
        )
        logger.info("RabbitMQ publisher connected")

    async def disconnect(self) -> None:
        if self._connection:
            await self._connection.close()

    async def publish_evaluation_task(
        self,
        submission_id: uuid.UUID,
        session_question_id: uuid.UUID,
        code: str,
        language: str,
        question_id: uuid.UUID,
    ) -> None:
        """
        Публикуем задачу оценки кода.
        AI Worker получит это сообщение и вызовет LLM для оценки.
        """
        message = {
            "submission_id": str(submission_id),
            "session_question_id": str(session_question_id),
            "question_id": str(question_id),
            "code": code,
            "language": language,
        }
        await self._publish(settings.evaluation_queue, message)
        logger.info("Published evaluation task", submission_id=str(submission_id))

    async def _publish(self, queue_name: str, payload: dict[str, Any]) -> None:
        if not self._channel:
            raise RuntimeError("RabbitMQ not connected")

        await self._channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,  # не теряем при перезапуске
                content_type="application/json",
            ),
            routing_key=queue_name,
        )


# Singleton — один publisher на всё приложение
publisher = RabbitMQPublisher()
