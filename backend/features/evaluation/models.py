"""features/evaluation/models.py — Pydantic models for the evaluation slice.

Migrated verbatim from main.py.  No field names or types changed so the
existing API contract is fully preserved.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EvalRequest(BaseModel):
    question_id: str
    answer: str
    provider: str = "ollama"
    api_key: str = ""
    model: str = ""
    # For dynamically generated questions (AI-generated, file-generated, interview)
    # the id won't be in the static catalogue — pass the text and section directly.
    question_text: str = ""
    section: str = ""
    # Optional: pass the candidate profile so evaluation is role-aware.
    # Either inline (`profile`) or by reference (`interview_session_id`).
    profile: dict | None = None
    interview_session_id: str = ""


class EvalResult(BaseModel):
    score: int
    verdict: str
    strength: str
    missing: str
    gaps: list[str] = Field(default_factory=list)
    hint: str
    ideal: str


class GenerateFollowUpRequest(BaseModel):
    original_question: str
    user_answer: str
    topic: str = ""
    provider: str = "groq"
    api_key: str = ""
    model: str = ""
    profile: dict | None = None
    interview_session_id: str = ""


class GenerateFollowUpResponse(BaseModel):
    follow_up_question: str


class EvaluateFollowUpRequest(BaseModel):
    original_question: str
    follow_up_question: str
    answer: str
    provider: str = "groq"
    api_key: str = ""
    model: str = ""
    profile: dict | None = None
    interview_session_id: str = ""


class EvaluateFollowUpResponse(BaseModel):
    clarified: bool
    feedback: str
