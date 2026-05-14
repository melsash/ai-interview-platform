import os
from celery import Celery
from celery.utils.log import get_task_logger

broker_url = os.getenv("CELERY_BROKER_URL", "amqp://rmq_user:rmq_pass@rabbitmq:5672/interview_vhost")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://:redis_pass@redis:6379/3")

app = Celery(
    "ai_worker",
    broker=broker_url,
    backend=result_backend,
    include=["app.tasks"],
)

app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Важно для надёжности:
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # один task за раз — честная очередь
    result_expires=3600,           # результаты хранятся 1 час
)
