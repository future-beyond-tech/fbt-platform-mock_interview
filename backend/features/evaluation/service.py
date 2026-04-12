"""features/evaluation/service.py — EvaluationService.

Thin orchestration layer: resolves the session profile (if an
interview_session_id was passed), delegates to the provider functions in
providers.py, and returns typed results.  All scoring/prompt logic stays in
providers.py for now (Phase 3 goal is routing + isolation, not rewriting
the scoring algorithm).
"""

from __future__ import annotations

import httpx

from providers import (
    ClientInputError,
    ProviderResponseError,
    evaluate_with_provider,
    evaluate_followup_with_provider,
    generate_followup_question_with_provider,
)
from features.evaluation.models import (
    EvalRequest,
    EvalResult,
    GenerateFollowUpRequest,
    EvaluateFollowUpRequest,
)


class EvaluationService:
    """Handles answer evaluation and follow-up question flow."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client

    # ── Core evaluation ───────────────────────────────────────────────────────

    async def evaluate(
        self,
        request: EvalRequest,
        *,
        question_text: str,
        section_text: str,
        profile: dict | None = None,
    ) -> dict:
        """Evaluate a candidate answer.  Returns the raw result dict from the LLM."""
        return await evaluate_with_provider(
            client=self._client,
            provider=request.provider,
            api_key=request.api_key,
            model=request.model,
            section=section_text,
            question=question_text,
            answer=request.answer,
            profile=profile,
        )

    # ── Follow-up question generation ─────────────────────────────────────────

    async def generate_followup(
        self,
        request: GenerateFollowUpRequest,
        *,
        profile: dict | None = None,
    ) -> str:
        """Generate one probing follow-up question for a partial answer."""
        return await generate_followup_question_with_provider(
            client=self._client,
            provider=request.provider,
            api_key=request.api_key,
            model=request.model,
            original_question=request.original_question.strip(),
            user_answer=request.user_answer.strip(),
            topic=request.topic.strip(),
            profile=profile,
        )

    # ── Follow-up evaluation ──────────────────────────────────────────────────

    async def evaluate_followup(
        self,
        request: EvaluateFollowUpRequest,
        *,
        profile: dict | None = None,
    ) -> dict:
        """Evaluate whether a follow-up answer clarifies understanding."""
        return await evaluate_followup_with_provider(
            client=self._client,
            provider=request.provider,
            api_key=request.api_key,
            model=request.model,
            original_question=request.original_question.strip(),
            follow_up_question=request.follow_up_question.strip(),
            answer=request.answer.strip(),
            profile=profile,
        )
