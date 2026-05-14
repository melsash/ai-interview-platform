from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    environment: str = "development"

    # Database (для сохранения результатов)
    database_url: str

    # Celery
    celery_broker_url: str
    celery_result_backend: str

    # Redis (для кэша и pub/sub)
    redis_url: str

    # RabbitMQ
    rabbitmq_url: str

    # OpenAI
    openai_api_key: str = ""

    # Queues
    evaluation_queue: str = "assessment.evaluate"
    feedback_queue: str = "assessment.feedback"

    # Timeouts
    code_execution_timeout_seconds: int = 30
    ai_evaluation_timeout_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
