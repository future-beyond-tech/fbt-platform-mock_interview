"""features/questions/models.py — Pydantic models for the questions slice."""

from __future__ import annotations

from pydantic import BaseModel


class GenerateQuestionsRequest(BaseModel):
    provider: str = "groq"
    api_key: str = ""
    model: str = ""
    topic: str = ""
    count: int = 3


class GenerateQuestionsResponse(BaseModel):
    questions: list[dict]
