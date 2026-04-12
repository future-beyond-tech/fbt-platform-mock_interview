"""features/evaluation/router.py — FastAPI router for evaluation endpoints.

Moves POST /api/evaluate, /api/generate-followup, and /api/evaluate-followup
out of main.py into this self-contained slice.  The routes are registered in
app.py via include_router().

Zero API contract changes: same paths, same request/response shapes.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from providers import (
    ClientInputError,
    ProviderResponseError,
)
from features.evaluation.models import (
    EvalRequest,
    EvalResult,
    GenerateFollowUpRequest,
    GenerateFollowUpResponse,
    EvaluateFollowUpRequest,
    EvaluateFollowUpResponse,
)
from features.evaluation.service import EvaluationService

router = APIRouter(prefix="/api", tags=["evaluation"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _http_client(request: Request) -> httpx.AsyncClient:
    """Pull the shared AsyncClient from app state."""
    return request.app.state.http_client


def _session_store(request: Request):
    """Pull the session store from app state."""
    return request.app.state.session_store


def _http_error_detail(error: httpx.HTTPStatusError) -> str:
    body = error.response.text[:200] if error.response is not None else str(error)
    return body or str(error)


def _resolve_question(req: EvalRequest) -> tuple[str, str]:
    """Return (question_text, section_text) or raise HTTPException."""
    from questions import QUESTIONS as _QUESTIONS
    question = next((q for q in _QUESTIONS if q["id"] == req.question_id), None)
    if question:
        return question["q"], question["s"]
    if req.question_text.strip():
        return req.question_text.strip(), req.section.strip() or "Interview"
    raise HTTPException(status_code=404, detail="Question not found")


def _resolve_profile(req: EvalRequest | GenerateFollowUpRequest | EvaluateFollowUpRequest, store) -> dict | None:
    """Merge session profile with inline profile; session wins."""
    profile = req.profile
    if req.interview_session_id:
        session = store.get(req.interview_session_id)
        if session and session.get("profile"):
            profile = session["profile"]
    return profile


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/evaluate", response_model=EvalResult)
async def evaluate(req: EvalRequest, request: Request):
    if not req.answer.strip():
        raise HTTPException(status_code=400, detail="Answer is required")

    question_text, section_text = _resolve_question(req)
    client = _http_client(request)
    store = _session_store(request)
    profile = _resolve_profile(req, store)

    service = EvaluationService(client)
    try:
        result = await service.evaluate(
            req,
            question_text=question_text,
            section_text=section_text,
            profile=profile,
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except ProviderResponseError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cannot reach the provider. Is Ollama running?"
                if req.provider == "ollama"
                else "Cannot reach the provider API."
            ),
        )
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Provider error: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Provider error: {error}")

    if result is None:
        raise HTTPException(status_code=422, detail="LLM returned unparseable response")

    # Persist the answer into the interview session if one is active.
    if req.interview_session_id:
        session = store.get(req.interview_session_id)
        if session is not None:
            state = session.get("state") or {}
            question_number = int(state.get("currentQuestionNumber") or 0)
            category = str(state.get("current_question_category") or "")
            if question_number > 0:
                from shared.interview_utils import upsert_interview_answer, build_interview_answer_record
                upsert_interview_answer(
                    state,
                    build_interview_answer_record(
                        question_number=question_number,
                        question_text=question_text,
                        answer_text=req.answer.strip(),
                        category=category,
                        section_text=section_text,
                        result=result,
                    ),
                )
                store.set(req.interview_session_id, session)

    return result


@router.post("/generate-followup", response_model=GenerateFollowUpResponse)
async def generate_followup(req: GenerateFollowUpRequest, request: Request):
    oq = (req.original_question or "").strip()
    ua = (req.user_answer or "").strip()
    if not oq:
        raise HTTPException(status_code=400, detail="original_question is required")
    if not ua:
        raise HTTPException(status_code=400, detail="user_answer is required")

    client = _http_client(request)
    store = _session_store(request)
    profile = _resolve_profile(req, store)

    service = EvaluationService(client)
    try:
        text = await service.generate_followup(req, profile=profile)
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except ProviderResponseError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cannot reach the provider. Is Ollama running?"
                if req.provider == "ollama"
                else "Cannot reach the provider API."
            ),
        )
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Provider error: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Provider error: {error}")

    return GenerateFollowUpResponse(follow_up_question=text)


@router.post("/evaluate-followup", response_model=EvaluateFollowUpResponse)
async def evaluate_followup(req: EvaluateFollowUpRequest, request: Request):
    if not (req.answer or "").strip():
        raise HTTPException(status_code=400, detail="answer is required")
    if not (req.follow_up_question or "").strip() or not (req.original_question or "").strip():
        raise HTTPException(
            status_code=400,
            detail="original_question and follow_up_question are required",
        )

    client = _http_client(request)
    store = _session_store(request)
    profile = _resolve_profile(req, store)

    service = EvaluationService(client)
    try:
        out = await service.evaluate_followup(req, profile=profile)
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except ProviderResponseError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cannot reach the provider. Is Ollama running?"
                if req.provider == "ollama"
                else "Cannot reach the provider API."
            ),
        )
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Provider error: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Provider error: {error}")

    return EvaluateFollowUpResponse(
        clarified=bool(out.get("clarified")),
        feedback=out.get("feedback") or "",
    )
