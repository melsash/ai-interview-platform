import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer,
    String, Text, Float, func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ---- Enums as string constants ----
# Используем str вместо Python Enum — проще сериализуется и хранится в БД

class QuestionDifficulty:
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class QuestionType:
    CODING = "coding"           # написать код
    SYSTEM_DESIGN = "system_design"  # описать архитектуру
    BEHAVIORAL = "behavioral"   # поведенческий вопрос

class SessionStatus:
    PENDING = "pending"         # создана, не началась
    ACTIVE = "active"           # идёт прямо сейчас
    COMPLETED = "completed"     # завершена
    EXPIRED = "expired"         # истекло время

class SubmissionStatus:
    QUEUED = "queued"           # в очереди RabbitMQ
    EVALUATING = "evaluating"   # AI Worker обрабатывает
    COMPLETED = "completed"     # оценка готова
    FAILED = "failed"           # ошибка при оценке


class Question(Base):
    """
    Банк вопросов для интервью.
    Один вопрос может использоваться в множестве сессий.
    """
    __tablename__ = "questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    question_type: Mapped[str] = mapped_column(String(30), nullable=False, default="coding")
    topic: Mapped[str] = mapped_column(String(100), nullable=True)  # "arrays", "dp", "system design"

    # Для coding вопросов
    starter_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    solution_code: Mapped[str | None] = mapped_column(Text, nullable=True)  # скрыто от кандидата
    test_cases: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Пример test_cases:
    # {"cases": [{"input": "[1,2,3]", "expected": "6"}, ...]}

    # Мета
    time_limit_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relations
    session_questions: Mapped[list["SessionQuestion"]] = relationship(back_populates="question")


class InterviewSession(Base):
    """
    Сессия интервью — центральная сущность.
    Связывает кандидата, набор вопросов и результаты.
    """
    __tablename__ = "interview_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    interviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)

    # Время
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Итоговая оценка (заполняется после завершения)
    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relations
    session_questions: Mapped[list["SessionQuestion"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class SessionQuestion(Base):
    """
    M2M между сессией и вопросами.
    Хранит порядок вопросов и статус выполнения каждого.
    """
    __tablename__ = "session_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("questions.id"),
        nullable=False,
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relations
    session: Mapped["InterviewSession"] = relationship(back_populates="session_questions")
    question: Mapped["Question"] = relationship(back_populates="session_questions")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="session_question")


class Submission(Base):
    """
    Попытка решения вопроса кандидатом.
    Один вопрос — множество попыток (кандидат может отправлять несколько раз).
    После создания → публикуется в RabbitMQ → AI Worker оценивает.
    """
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("session_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Что прислал кандидат
    code: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)  # "python", "javascript"

    # Статус обработки
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)

    # Результат от AI Worker (заполняется асинхронно)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)           # 0.0 - 100.0
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)           # текстовый фидбек
    test_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)     # результаты тест-кейсов
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relations
    session_question: Mapped["SessionQuestion"] = relationship(back_populates="submissions")
