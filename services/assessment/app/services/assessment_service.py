import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.rabbitmq import publisher
from app.core.websocket import ws_manager
from app.models.assessment import SessionStatus, SubmissionStatus
from app.repositories.assessment_repository import (
    QuestionRepository, SessionRepository, SubmissionRepository,
)
from app.schemas.assessment import (
    QuestionCreate, SessionCreate, SubmissionCreate,
    WSMessage, WSMessageType,
)

settings = get_settings()


class QuestionService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = QuestionRepository(db)

    async def create(self, data: QuestionCreate, created_by: uuid.UUID) -> object:
        return await self.repo.create(
            **data.model_dump(),
            created_by=created_by,
        )

    async def list_active(self, limit: int = 50, offset: int = 0) -> list:
        return await self.repo.list_active(limit=limit, offset=offset)

    async def get_by_id(self, question_id: uuid.UUID) -> object:
        q = await self.repo.get_by_id(question_id)
        if not q:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
        return q


class SessionService:
    def __init__(self, db: AsyncSession) -> None:
        self.session_repo = SessionRepository(db)
        self.question_repo = QuestionRepository(db)

    async def create_session(self, data: SessionCreate, interviewer_id: uuid.UUID) -> object:
        # Валидируем что все вопросы существуют
        questions = await self.question_repo.get_many_by_ids(data.question_ids)
        if len(questions) != len(data.question_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more questions not found",
            )

        session = await self.session_repo.create(
            candidate_id=data.candidate_id,
            interviewer_id=interviewer_id,
            title=data.title,
            status=SessionStatus.PENDING,
            scheduled_at=data.scheduled_at,
        )

        await self.session_repo.add_questions(session.id, data.question_ids)
        return session

    async def start_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> dict:
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if session.candidate_id != user_id and session.interviewer_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")

        if session.status != SessionStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail=f"Session cannot be started (current status: {session.status})",
            )

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.max_session_duration_minutes
        )

        await self.session_repo.update_status(
            session_id,
            SessionStatus.ACTIVE,
            started_at=datetime.now(timezone.utc),
            expires_at=expires_at,
        )

        session.status = SessionStatus.ACTIVE
        session.expires_at = expires_at

        return {
            "session": session,
            "websocket_url": f"ws://localhost:8002/ws/sessions/{session_id}",
            "expires_at": expires_at,
        }

    async def get_session_detail(self, session_id: uuid.UUID, user_id: uuid.UUID) -> object:
        session = await self.session_repo.get_with_questions(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.candidate_id != user_id and session.interviewer_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        return session

    async def list_my_sessions(self, candidate_id: uuid.UUID) -> list:
        return await self.session_repo.list_for_candidate(candidate_id)


class SubmissionService:
    def __init__(self, db: AsyncSession) -> None:
        self.submission_repo = SubmissionRepository(db)
        self.session_repo = SessionRepository(db)

    async def submit_code(
        self,
        session_id: uuid.UUID,
        session_question_id: uuid.UUID,
        data: SubmissionCreate,
        candidate_id: uuid.UUID,
    ) -> object:
        # Проверяем что сессия активна
        session = await self.session_repo.get_by_id(session_id)
        if not session or session.status != SessionStatus.ACTIVE:
            raise HTTPException(status_code=400, detail="Session is not active")

        if session.candidate_id != candidate_id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Создаём submission в БД
        submission = await self.submission_repo.create(
            session_question_id=session_question_id,
            candidate_id=candidate_id,
            code=data.code,
            language=data.language,
            status=SubmissionStatus.QUEUED,
        )

        # Получаем question_id для передачи в worker
        from sqlalchemy import select
        from app.models.assessment import SessionQuestion
        from app.core.database import AsyncSessionLocal

        # Публикуем в RabbitMQ — не ждём результата
        await publisher.publish_evaluation_task(
            submission_id=submission.id,
            session_question_id=session_question_id,
            code=data.code,
            language=data.language,
            question_id=submission.session_question_id,
        )

        # Уведомляем через WebSocket что задача поставлена в очередь
        await ws_manager.broadcast_to_session(
            session_id,
            {
                "type": WSMessageType.SUBMISSION_QUEUED,
                "data": {
                    "submission_id": str(submission.id),
                    "status": "queued",
                },
            },
        )

        return submission

    async def handle_evaluation_result(
        self,
        submission_id: uuid.UUID,
        session_id: uuid.UUID,
        score: float,
        feedback: str,
        test_results: dict,
        execution_time_ms: int,
        success: bool,
    ) -> None:
        """
        Вызывается когда AI Worker завершил оценку.
        Обновляет БД и пушит результат через WebSocket.
        """
        status = SubmissionStatus.COMPLETED if success else SubmissionStatus.FAILED

        await self.submission_repo.update_result(
            submission_id=submission_id,
            status=status,
            score=score,
            feedback=feedback,
            test_results=test_results,
            execution_time_ms=execution_time_ms,
        )

        # Realtime push — кандидат сразу видит результат
        await ws_manager.broadcast_to_session(
            session_id,
            {
                "type": WSMessageType.SUBMISSION_COMPLETED,
                "data": {
                    "submission_id": str(submission_id),
                    "score": score,
                    "feedback": feedback,
                    "test_results": test_results,
                    "status": status,
                },
            },
        )
