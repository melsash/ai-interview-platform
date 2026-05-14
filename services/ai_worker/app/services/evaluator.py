import json
import structlog
from openai import AsyncOpenAI

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


# Промпт для оценки кода — это и есть "AI" в платформе
EVALUATION_SYSTEM_PROMPT = """You are an expert software engineer conducting a technical interview.
Your task is to evaluate a candidate's code solution.

You must respond with ONLY a valid JSON object, no markdown, no explanation outside JSON.

Evaluate the code on these criteria:
- correctness: does it solve the problem correctly?
- code_quality: is it clean, readable, well-structured?
- efficiency: time and space complexity
- edge_cases: are edge cases handled?

Response format:
{
  "score": <float 0-100>,
  "passed_tests": <int>,
  "total_tests": <int>,
  "time_complexity": "<e.g. O(n)>",
  "space_complexity": "<e.g. O(1)>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "improvements": ["<improvement 1>", "<improvement 2>"],
  "feedback": "<detailed paragraph feedback for the candidate>",
  "test_results": [
    {"test_case": "<input>", "expected": "<output>", "passed": <bool>, "note": "<note>"}
  ]
}"""


class AIEvaluationService:
    """
    Сервис оценки кода с помощью OpenAI.

    Паттерн:
    1. Получаем код кандидата + описание задачи
    2. Формируем промпт
    3. Отправляем в OpenAI GPT-4
    4. Парсим структурированный JSON ответ
    5. Возвращаем результат

    Если OpenAI API недоступен (нет ключа) — используем mock оценку.
    Это важно для dev/demo окружения.
    """

    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def evaluate(
        self,
        code: str,
        language: str,
        question_title: str,
        question_description: str,
        test_cases: dict | None = None,
    ) -> dict:
        """Main evaluation entry point."""
        if not self.client or not settings.openai_api_key:
            logger.warning("OpenAI key not configured, using mock evaluation")
            return self._mock_evaluation(code, language)

        try:
            return await self._openai_evaluate(
                code, language, question_title, question_description, test_cases
            )
        except Exception as e:
            logger.error("OpenAI evaluation failed", error=str(e))
            return self._mock_evaluation(code, language)

    async def _openai_evaluate(
        self,
        code: str,
        language: str,
        question_title: str,
        question_description: str,
        test_cases: dict | None,
    ) -> dict:
        user_prompt = f"""
Question: {question_title}

Description:
{question_description}

Candidate's solution ({language}):
```{language}
{code}
```

{"Test cases: " + json.dumps(test_cases) if test_cases else ""}

Evaluate this solution and respond with JSON only.
"""
        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",   # быстрый и дешёвый для оценки
            messages=[
                {"role": "system", "content": EVALUATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,       # низкая температура = детерминированный результат
            max_tokens=1000,
            timeout=settings.ai_evaluation_timeout_seconds,
        )

        raw = response.choices[0].message.content.strip()

        # Убираем markdown блоки если модель всё же добавила
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        result = json.loads(raw)
        logger.info("OpenAI evaluation complete", score=result.get("score"))
        return result

    def _mock_evaluation(self, code: str, language: str) -> dict:
        """
        Mock оценка для dev окружения без OpenAI ключа.
        Анализирует код эвристически — длина, наличие базовых конструкций.
        """
        lines = [l for l in code.strip().split("\n") if l.strip()]
        line_count = len(lines)

        # Простая эвристика
        has_function = "def " in code or "function " in code or "func " in code
        has_loop = any(k in code for k in ["for ", "while "])
        has_return = "return " in code
        has_comments = "#" in code or "//" in code

        score = 40.0
        if has_function: score += 15
        if has_loop: score += 10
        if has_return: score += 15
        if has_comments: score += 5
        if line_count > 5: score += 5
        if line_count > 15: score += 10

        score = min(score, 95.0)

        return {
            "score": round(score, 1),
            "passed_tests": 3,
            "total_tests": 5,
            "time_complexity": "O(n)",
            "space_complexity": "O(1)",
            "strengths": [
                "Code is structured with proper function definition",
                "Logic flow is clear and readable",
            ],
            "improvements": [
                "Consider adding input validation",
                "Edge cases like empty input could be handled",
                "Add docstring to document the function",
            ],
            "feedback": (
                f"Your {language} solution demonstrates a good understanding of the problem. "
                f"The implementation covers the main cases. "
                f"Consider improving error handling and adding comments for better readability. "
                f"Overall score: {round(score, 1)}/100."
            ),
            "test_results": [
                {"test_case": "basic input", "expected": "correct output", "passed": True, "note": "Passed"},
                {"test_case": "edge case", "expected": "edge output", "passed": score > 60, "note": "Partially passed"},
            ],
        }
