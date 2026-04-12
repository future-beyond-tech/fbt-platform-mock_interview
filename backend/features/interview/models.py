"""features/interview/models.py — Pydantic request/response models for interview endpoints.

Extracted verbatim from main.py.  Zero API contract changes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class InterviewTurnRequest(BaseModel):
    session_id: str
    answer: str
    provider: str = "gemini"
    api_key: str = ""
    model: str = ""


class EnqueueProbeRequest(BaseModel):
    """Queue a probing question (same style as a normal tier question) after a partial tier answer."""
    session_id: str
    original_question: str
    user_answer: str
    category: str  # tier_1 | tier_2 | tier_3
    provider: str = "gemini"
    api_key: str = ""
    model: str = ""


class InterviewReportRequest(BaseModel):
    session_id: str
    provider: str = "gemini"
    api_key: str = ""
    model: str = ""
    answers: list[dict] = Field(default_factory=list)
