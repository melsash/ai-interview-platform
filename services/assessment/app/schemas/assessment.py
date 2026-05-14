import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---- Question schemas ----

class QuestionCreate(BaseModel):
    title: str = Field(min_length=5, max_length=500)
    description: str = Field(min_length=10)
    difficulty: str = Field(default="medium")
    question_type: str = Field(default="coding")
    topic: str | None = None
    starter_code: str | None = None
    test_cases: dict | None = None
    time_limit_minutes: int = Field(default=30, ge=5, le=180)

class QuestionResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    difficulty: str
    question_type: str
    topic: str | None
    starter_code: str | None
    time_limit_minutes: int
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# ---- Session schemas ----

class SessionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    candidate_id: uuid.UUID
    question_ids: list[uuid.UUID] = Field(min_length=1, max_length=10)
    scheduled_at: datetime | None = None

class SessionResponse(BaseModel):
    id: uuid.UUID
    candidate_id: uuid.UUID
    interviewer_id: uuid.UUID | None
    title: str
    status: str
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None
    total_score: float | None
    created_at: datetime
    model_config = {"from_attributes": True}

class SessionDetailResponse(SessionResponse):
    """Детальный ответ — включает вопросы."""
    questions: list[QuestionResponse] = []

class SessionStartResponse(BaseModel):
    session: SessionResponse
    websocket_url: str   # ws://host/ws/sessions/{id}
    expires_at: datetime


# ---- Submission schemas ----

class SubmissionCreate(BaseModel):
    code: str = Field(min_length=1)
    language: str = Field(default="python")

class SubmissionResponse(BaseModel):
    id: uuid.UUID
    session_question_id: uuid.UUID
    candidate_id: uuid.UUID
    code: str
    language: str
    status: str
    score: float | None
    feedback: str | None
    test_results: dict | None
    execution_time_ms: int | None
    submitted_at: datetime
    evaluated_at: datetime | None
    model_config = {"from_attributes": True}


# ---- WebSocket message schemas ----
# Эти схемы описывают формат сообщений через WebSocket

class WSMessageType:
    SUBMISSION_QUEUED = "submission.queued"
    SUBMISSION_EVALUATING = "submission.evaluating"
    SUBMISSION_COMPLETED = "submission.completed"
    SUBMISSION_FAILED = "submission.failed"
    SESSION_COMPLETED = "session.completed"
    ERROR = "error"

class WSMessage(BaseModel):
    type: str
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
