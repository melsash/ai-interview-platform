import uuid
from datetime import datetime, timezone

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal


async def save_evaluation_result(
    submission_id: uuid.UUID,
    score: float,
    feedback: str,
    test_results: dict,
    execution_time_ms: int,
    status: str = "completed",
) -> None:
    """
    Сохраняем результат оценки в assessment БД.
    AI Worker пишет напрямую в assessment.submissions таблицу.

    В production лучше через internal API, но для MVP прямое подключение к БД проще.
    """
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("""
                UPDATE submissions
                SET status = :status,
                    score = :score,
                    feedback = :feedback,
                    test_results = :test_results::jsonb,
                    execution_time_ms = :execution_time_ms,
                    evaluated_at = :evaluated_at
                WHERE id = :submission_id
            """),
            {
                "submission_id": str(submission_id),
                "status": status,
                "score": score,
                "feedback": feedback,
                "test_results": __import__("json").dumps(test_results),
                "execution_time_ms": execution_time_ms,
                "evaluated_at": datetime.now(timezone.utc),
            }
        )
        await session.commit()
