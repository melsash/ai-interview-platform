import asyncio
import time
import uuid

import structlog

from app.worker import app
from app.core.redis_client import publish_result
from app.services.evaluator import AIEvaluationService
from app.services.result_repository import save_evaluation_result

logger = structlog.get_logger()


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@app.task(
    name="assessment.evaluate",
    queue="assessment.evaluate",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def evaluate_submission(
    self,
    submission_id: str,
    session_question_id: str,
    code: str,
    language: str,
    question_id: str,
    question_title: str = "Coding Challenge",
    question_description: str = "Solve the given problem.",
    test_cases: dict | None = None,
) -> dict:
    """
    Main evaluation task.
    Pipeline: RabbitMQ -> AI evaluation -> save to DB -> publish to Redis -> WebSocket -> candidate
    acks_late=True: if worker crashes, RabbitMQ returns task to queue.
    """
    logger.info("Starting evaluation", submission_id=submission_id, language=language)
    start_time = time.time()

    try:
        evaluator = AIEvaluationService()
        result = run_async(evaluator.evaluate(
            code=code,
            language=language,
            question_title=question_title,
            question_description=question_description,
            test_cases=test_cases,
        ))

        execution_time_ms = int((time.time() - start_time) * 1000)

        run_async(save_evaluation_result(
            submission_id=uuid.UUID(submission_id),
            score=result["score"],
            feedback=result["feedback"],
            test_results=result,
            execution_time_ms=execution_time_ms,
            status="completed",
        ))

        run_async(publish_result({
            "submission_id": submission_id,
            "session_question_id": session_question_id,
            "status": "completed",
            "score": result["score"],
            "feedback": result["feedback"],
            "test_results": result.get("test_results", []),
            "time_complexity": result.get("time_complexity"),
            "space_complexity": result.get("space_complexity"),
            "strengths": result.get("strengths", []),
            "improvements": result.get("improvements", []),
            "execution_time_ms": execution_time_ms,
        }))

        logger.info("Evaluation complete", submission_id=submission_id, score=result["score"])
        return {"status": "completed", "score": result["score"]}

    except Exception as exc:
        logger.error("Evaluation failed", submission_id=submission_id, error=str(exc))
        try:
            run_async(save_evaluation_result(
                submission_id=uuid.UUID(submission_id),
                score=0.0,
                feedback="Evaluation failed due to an internal error.",
                test_results={},
                execution_time_ms=int((time.time() - start_time) * 1000),
                status="failed",
            ))
            run_async(publish_result({"submission_id": submission_id, "status": "failed", "error": str(exc)}))
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=10 * (self.request.retries + 1))


@app.task(name="assessment.feedback", queue="assessment.feedback", bind=True, max_retries=2)
def generate_detailed_feedback(self, submission_id: str, evaluation_result: dict) -> dict:
    score = evaluation_result.get("score", 0)
    if score >= 90:
        summary = "Excellent solution! Strong problem-solving skills demonstrated."
    elif score >= 70:
        summary = "Good solution with room for improvement."
    elif score >= 50:
        summary = "Partial solution. Review the improvements and try again."
    else:
        summary = "Solution needs significant work. Focus on the core algorithm first."
    return {"submission_id": submission_id, "summary": summary, "score": score}
