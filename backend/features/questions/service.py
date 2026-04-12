"""features/questions/service.py — QuestionService."""

from __future__ import annotations

import httpx

from providers import generate_questions_with_provider
from features.questions.data import QUESTIONS, SESSIONS
from features.questions.models import GenerateQuestionsRequest


class QuestionService:
    """Handles static catalogue retrieval and AI-generated question creation."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client

    def get_all(self, day: int | None = None) -> list[dict]:
        """Return the static question catalogue, optionally filtered by day."""
        if day is None:
            return QUESTIONS
        return [q for q in QUESTIONS if q.get("day") == day]

    def get_sessions(self) -> list[dict]:
        """Return the session presets."""
        return SESSIONS

    async def generate(self, request: GenerateQuestionsRequest) -> list[dict]:
        """Generate questions using the selected LLM provider."""
        count = max(1, min(10, request.count))
        return await generate_questions_with_provider(
            client=self._client,
            provider=request.provider,
            api_key=request.api_key,
            model=request.model,
            topic=request.topic,
            count=count,
        )
