import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assessment import (
    InterviewSession, Question, SessionQuestion, Submission,
)


class QuestionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, **kwargs) -> Question:
        q = Question(**kwargs)
        self.db.add(q)
        await self.db.flush()
        await self.db.refresh(q)
        return q

    async def get_by_id(self, question_id: uuid.UUID) -> Question | None:
        result = await self.db.execute(select(Question).where(Question.id == question_id))
        return result.scalar_one_or_none()

    async def get_many_by_ids(self, ids: list[uuid.UUID]) -> list[Question]:
        result = await self.db.execute(select(Question).where(Question.id.in_(ids)))
        return list(result.scalars().all())

    async def list_active(self, limit: int = 50, offset: int = 0) -> list[Question]:
        result = await self.db.execute(
            select(Question)
            .where(Question.is_active.is_(True))
            .limit(limit)
            .offset(offset)
            .order_by(Question.created_at.desc())
        )
        return list(result.scalars().all())


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, **kwargs) -> InterviewSession:
        session = InterviewSession(**kwargs)
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def get_by_id(self, session_id: uuid.UUID) -> InterviewSession | None:
        result = await self.db.execute(
            select(InterviewSession).where(InterviewSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_with_questions(self, session_id: uuid.UUID) -> InterviewSession | None:
        """Eager load questions — избегаем N+1 проблему."""
        result = await self.db.execute(
            select(InterviewSession)
            .options(
                selectinload(InterviewSession.session_questions)
                .selectinload(SessionQuestion.question)
            )
            .where(InterviewSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_for_candidate(self, candidate_id: uuid.UUID) -> list[InterviewSession]:
        result = await self.db.execute(
            select(InterviewSession)
            .where(InterviewSession.candidate_id == candidate_id)
            .order_by(InterviewSession.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(self, session_id: uuid.UUID, status: str, **extra) -> None:
        values = {"status": status, **extra}
        await self.db.execute(
            update(InterviewSession)
            .where(InterviewSession.id == session_id)
            .values(**values)
        )

    async def add_questions(
        self, session_id: uuid.UUID, question_ids: list[uuid.UUID]
    ) -> list[SessionQuestion]:
        session_questions = [
            SessionQuestion(
                session_id=session_id,
                question_id=qid,
                order_index=idx,
            )
            for idx, qid in enumerate(question_ids)
        ]
        for sq in session_questions:
            self.db.add(sq)
        await self.db.flush()
        return session_questions


class SubmissionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, **kwargs) -> Submission:
        submission = Submission(**kwargs)
        self.db.add(submission)
        await self.db.flush()
        await self.db.refresh(submission)
        return submission

    async def get_by_id(self, submission_id: uuid.UUID) -> Submission | None:
        result = await self.db.execute(
            select(Submission).where(Submission.id == submission_id)
        )
        return result.scalar_one_or_none()

    async def update_result(
        self,
        submission_id: uuid.UUID,
        status: str,
        score: float | None = None,
        feedback: str | None = None,
        test_results: dict | None = None,
        execution_time_ms: int | None = None,
    ) -> None:
        await self.db.execute(
            update(Submission)
            .where(Submission.id == submission_id)
            .values(
                status=status,
                score=score,
                feedback=feedback,
                test_results=test_results,
                execution_time_ms=execution_time_ms,
                evaluated_at=datetime.now(timezone.utc),
            )
        )

    async def get_session_question_id(self, submission_id: uuid.UUID) -> uuid.UUID | None:
        result = await self.db.execute(
            select(Submission.session_question_id)
            .where(Submission.id == submission_id)
        )
        return result.scalar_one_or_none()
