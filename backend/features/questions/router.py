"""features/questions/router.py — FastAPI router for question endpoints.

Moves GET /api/questions and POST /api/generate-questions out of main.py.
Zero API contract changes.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request

from providers import ClientInputError, ProviderResponseError
from features.questions.models import GenerateQuestionsRequest
from features.questions.service import QuestionService

router = APIRouter(prefix="/api", tags=["questions"])


def _http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def _http_error_detail(error: httpx.HTTPStatusError) -> str:
    body = error.response.text[:200] if error.response is not None else str(error)
    return body or str(error)


@router.get("/questions")
async def get_questions(request: Request):
    service = QuestionService(_http_client(request))
    return {"questions": service.get_all(), "sessions": service.get_sessions()}


@router.post("/generate-questions")
async def generate_questions(req: GenerateQuestionsRequest, request: Request):
    """Generate fresh interview questions using the selected LLM provider."""
    service = QuestionService(_http_client(request))
    try:
        questions = await service.generate(req)
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except ProviderResponseError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Generation failed: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Generation failed: {error}")

    if not questions:
        raise HTTPException(status_code=422, detail="LLM returned no valid questions")

    return {"questions": questions}
