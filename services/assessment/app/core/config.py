from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "AI Interview — Assessment Service"
    environment: str = "development"
    debug: bool = False

    database_url: str
    redis_url: str
    rabbitmq_url: str
    auth_service_url: str = "http://auth:8000"

    # RabbitMQ queues
    evaluation_queue: str = "assessment.evaluate"
    feedback_queue: str = "assessment.feedback"

    # Session settings
    max_session_duration_minutes: int = 90
    code_execution_timeout_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
