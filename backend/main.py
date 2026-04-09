"""
Sheikh Mock Interviewer — Multi-provider FastAPI backend.
Supports: Ollama (local), Google Gemini, Groq, OpenAI, Anthropic.

Run:  uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import os

from dotenv import load_dotenv

# Load .env from the project root (one level up from backend/) first,
# then fall back to backend/.env if present. Either way, variables that are
# already set in the real environment take precedence.
_PROJECT_ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
_BACKEND_ENV = Path(__file__).resolve().parent / ".env"
if _PROJECT_ROOT_ENV.exists():
    load_dotenv(_PROJECT_ROOT_ENV, override=False)
if _BACKEND_ENV.exists():
    load_dotenv(_BACKEND_ENV, override=False)

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from questions import QUESTIONS, SESSIONS
from providers import (
    ClientInputError,
    ProviderResponseError,
    evaluate_with_provider,
    extract_insights_from_answer,
    extract_profile_from_resume,
    generate_question_from_file,
    generate_questions_with_provider,
    interview_next_question,
    resolve_api_key,
)
from providers import _extract_pdf_text  # noqa: PLC2701 — internal helper reused

# ── HTTP client (shared) ──
http_client: httpx.AsyncClient | None = None

DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
}
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"}
SERVER_KEY_ENV_VARS = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def _cors_origins() -> list[str]:
    raw = os.environ.get("BACKEND_CORS_ORIGINS", ",".join(DEFAULT_CORS_ORIGINS)).strip()
    if raw == "*":
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def _http_error_detail(error: httpx.HTTPStatusError) -> str:
    body = error.response.text[:200] if error.response is not None else str(error)
    return body or str(error)


def _has_server_key(provider_id: str) -> bool:
    env_name = SERVER_KEY_ENV_VARS.get(provider_id)
    return bool(env_name and os.environ.get(env_name, "").strip())


def _validate_upload(file_bytes: bytes, content_type: str, filename: str) -> None:
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large — max 10 MB.")

    suffix = Path(filename or "").suffix.lower()
    content_type = (content_type or "").lower()
    valid_content_type = content_type in ALLOWED_UPLOAD_CONTENT_TYPES
    valid_suffix = suffix in ALLOWED_UPLOAD_EXTENSIONS

    if not (valid_content_type or valid_suffix):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload a PDF or image (PNG, JPG, WEBP, GIF).",
        )


async def _fetch_ollama_models() -> list[str]:
    if http_client is None:
        return []

    try:
        response = await http_client.get("http://localhost:11434/api/tags")
        response.raise_for_status()
        return [model["name"] for model in response.json().get("models", [])]
    except Exception:
        return []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0))
    print("[OK] Sheikh Mock backend ready - multi-provider mode")

    try:
        models = await _fetch_ollama_models()
        if models:
            print(f"  Ollama connected - models: {models}")
        else:
            print("  Ollama not running (optional - cloud providers still work)")
    except httpx.ConnectError:
        print("  Ollama not running (optional - cloud providers still work)")

    yield
    await http_client.aclose()


app = FastAPI(title="Sheikh Mock API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


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


class GenerateQuestionsRequest(BaseModel):
    provider: str = "groq"
    api_key: str = ""
    model: str = ""
    topic: str = ""
    count: int = 3


class EvalResult(BaseModel):
    score: int
    verdict: str
    strength: str
    missing: str
    hint: str
    ideal: str


class ProviderInfo(BaseModel):
    id: str
    name: str
    needs_key: bool
    server_key_available: bool = False
    default_model: str
    models: list[str]


@app.get("/api/health")
async def health():
    ollama_models = await _fetch_ollama_models()
    return {
        "status": "ok" if http_client is not None else "unreachable",
        "ollama": bool(ollama_models),
        "ollama_models": ollama_models,
    }


@app.get("/api/providers")
async def get_providers():
    """Return available providers and their config."""
    ollama_models = await _fetch_ollama_models()

    providers = [
        ProviderInfo(
            id="ollama",
            name="Ollama (Local)",
            needs_key=False,
            default_model=ollama_models[0] if ollama_models else "llama3:latest",
            models=ollama_models or ["llama3:latest"],
        ),
        ProviderInfo(
            id="gemini",
            name="Google Gemini",
            needs_key=True,
            server_key_available=_has_server_key("gemini"),
            default_model="gemini-2.5-flash",
            models=[
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-2.5-pro",
                "gemma-3-27b-it",
                "gemma-3-12b-it",
                "gemma-3-4b-it",
            ],
        ),
        ProviderInfo(
            id="groq",
            name="Groq",
            needs_key=True,
            server_key_available=_has_server_key("groq"),
            default_model="llama-3.3-70b-versatile",
            models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "qwen-qwq-32b", "gemma2-9b-it"],
        ),
        ProviderInfo(
            id="openai",
            name="OpenAI",
            needs_key=True,
            server_key_available=_has_server_key("openai"),
            default_model="gpt-4o-mini",
            models=["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1-nano"],
        ),
        ProviderInfo(
            id="anthropic",
            name="Anthropic",
            needs_key=True,
            server_key_available=_has_server_key("anthropic"),
            default_model="claude-sonnet-4-20250514",
            models=["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"],
        ),
    ]
    return {"providers": providers}


@app.get("/api/questions")
async def get_questions():
    return {"questions": QUESTIONS, "sessions": SESSIONS}


@app.post("/api/evaluate", response_model=EvalResult)
async def evaluate(req: EvalRequest):
    if not req.answer.strip():
        raise HTTPException(status_code=400, detail="Answer is required")

    question = next((q for q in QUESTIONS if q["id"] == req.question_id), None)
    if question:
        section_text = question["s"]
        question_text = question["q"]
    elif req.question_text.strip():
        # Dynamically generated question — use the text the client sent.
        section_text = req.section.strip() or "Interview"
        question_text = req.question_text.strip()
    else:
        raise HTTPException(status_code=404, detail="Question not found")

    # Resolve the profile: prefer the live interview session over an inline payload.
    profile: dict | None = req.profile
    if req.interview_session_id:
        sess = INTERVIEW_SESSIONS.get(req.interview_session_id)
        if sess and sess.get("profile"):
            profile = sess["profile"]

    try:
        result = await evaluate_with_provider(
            client=http_client,
            provider=req.provider,
            api_key=req.api_key,
            model=req.model,
            section=section_text,
            question=question_text,
            answer=req.answer,
            profile=profile,
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except ProviderResponseError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Cannot reach the provider. Is Ollama running?" if req.provider == "ollama"
            else "Cannot reach the provider API.",
        )
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Provider error: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(error)}")

    if result is None:
        raise HTTPException(status_code=422, detail="LLM returned unparseable response")

    return result


@app.post("/api/generate-questions")
async def generate_questions(req: GenerateQuestionsRequest):
    """Generate fresh interview questions using the selected LLM provider."""
    count = max(1, min(10, req.count))
    try:
        questions = await generate_questions_with_provider(
            client=http_client,
            provider=req.provider,
            api_key=req.api_key,
            model=req.model,
            topic=req.topic,
            count=count,
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except ProviderResponseError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Generation failed: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Generation failed: {str(error)}")

    if not questions:
        raise HTTPException(status_code=422, detail="LLM returned no valid questions")

    return {"questions": questions}


@app.post("/api/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    groq_api_key: str = Form(""),
):
    """Transcribe audio using Groq Whisper large-v3-turbo."""
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")
    if len(audio_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large — max 10 MB.")

    try:
        resolved_key = resolve_api_key("groq", groq_api_key)
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))

    try:
        response = await http_client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {resolved_key}"},
            files={"file": (audio.filename or "audio.webm", audio_bytes, audio.content_type or "audio/webm")},
            data={
                "model": "whisper-large-v3-turbo",
                "response_format": "json",
                "language": "en",
            },
        )
        response.raise_for_status()
        data = response.json()
        return {"text": data.get("text", "").strip()}
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Groq Whisper error: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {str(error)}")


@app.post("/api/generate-from-file")
async def generate_from_file(
    file: UploadFile = File(...),
    provider: str = Form("groq"),
    api_key: str = Form(""),
    model: str = Form(""),
):
    """Extract text/content from a PDF or image and generate 1 interview question."""
    file_bytes = await file.read()
    content_type = file.content_type or ""
    filename = file.filename or ""
    _validate_upload(file_bytes, content_type, filename)

    try:
        question = await generate_question_from_file(
            client=http_client,
            provider=provider,
            api_key=api_key,
            model=model,
            file_bytes=file_bytes,
            content_type=content_type,
            filename=filename,
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except ProviderResponseError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"File question generation failed: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"File question generation failed: {str(error)}")

    return {"questions": [question]}


# ── Interview (multi-turn conversational) ──
import uuid

INTERVIEW_SESSIONS: dict[str, dict] = {}
MAX_INTERVIEW_TURNS = 14


def _initial_interview_state() -> dict:
    return {
        "phase": "introduction",
        "questionCount": 0,
        "extractedSkills": [],
        "extractedProjects": [],
        "questionsAsked": [],
        "difficultyLevel": 1,
        "lastAnswerQuality": None,
        "completed": False,
    }


def _next_difficulty(current: int, quality: str | None) -> int:
    if quality == "strong":
        return min(current + 1, 3)
    if quality == "weak":
        return max(current - 1, 1)
    return current


class InterviewTurnRequest(BaseModel):
    session_id: str
    answer: str
    provider: str = "gemini"
    api_key: str = ""
    model: str = ""


@app.post("/api/interview/start")
async def interview_start(
    file: UploadFile = File(...),
    provider: str = Form("gemini"),
    api_key: str = Form(""),
    model: str = Form(""),
):
    """Upload a resume PDF, create an interview session, return the opening question."""
    file_bytes = await file.read()
    content_type = file.content_type or ""
    filename = file.filename or ""
    _validate_upload(file_bytes, content_type, filename)

    is_pdf = "pdf" in content_type.lower() or filename.lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Interview mode requires a PDF resume.")

    try:
        resume_text = _extract_pdf_text(file_bytes)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {error}")

    if not resume_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from PDF.")

    chosen_model = model or "gemma-3-12b-it"

    # Step 1: extract a structured profile (domain, role, experience, isTechnical, ...).
    try:
        profile = await extract_profile_from_resume(
            client=http_client,
            provider=provider,
            api_key=api_key,
            model=chosen_model,
            resume_text=resume_text,
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        # Profile extraction is best-effort — fall back to a generic profile.
        print(f"[interview] profile extraction failed (non-fatal): {error}")
        profile = {
            "domain": "General Professional",
            "roles": ["Professional"],
            "yearsOfExperience": 0,
            "experienceLevel": "mid",
            "isTechnical": True,
            "topSkills": [],
            "notableProjects": [],
        }

    state = _initial_interview_state()
    # Seed the live state with what we already learned from the resume.
    state["extractedSkills"] = list(profile.get("topSkills") or [])
    state["extractedProjects"] = list(profile.get("notableProjects") or [])

    try:
        opening = await interview_next_question(
            client=http_client,
            provider=provider,
            api_key=api_key,
            model=chosen_model,
            state=state,
            resume_text=resume_text,
            history=[],
            profile=profile,
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except ProviderResponseError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Interview start failed: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Interview start failed: {str(error)}")

    state["questionsAsked"].append(opening)
    state["questionCount"] = 1

    session_id = uuid.uuid4().hex
    INTERVIEW_SESSIONS[session_id] = {
        "resume_text": resume_text,
        "history": [{"role": "assistant", "content": opening}],
        "state": state,
        "profile": profile,
        "provider": provider,
        "model": chosen_model,
    }

    return {
        "session_id": session_id,
        "question": opening,
        "section": "Introduction",
        "state": state,
        "profile": profile,
    }


@app.post("/api/interview/turn")
async def interview_turn(req: InterviewTurnRequest):
    """Submit a candidate answer; receive the next interviewer question + updated state."""
    session = INTERVIEW_SESSIONS.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found or expired.")

    answer = (req.answer or "").strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer is required.")

    state = session["state"]
    history: list[dict] = session["history"]
    resume_text: str = session["resume_text"]
    profile: dict | None = session.get("profile")
    # Allow per-turn override but fall back to session defaults.
    provider = req.provider or session["provider"]
    model = req.model or session["model"]
    api_key = req.api_key

    history.append({"role": "user", "content": answer})

    # Step 1: extract insights from this answer (lightweight, may fail gracefully)
    try:
        insights = await extract_insights_from_answer(
            client=http_client,
            provider=provider,
            api_key=api_key,
            model="gemma-3-4b-it" if provider == "gemini" else model,
            answer=answer,
            state=state,
        )
    except Exception as error:
        print(f"[interview] extract failed (non-fatal): {error}")
        insights = {"newSkills": [], "newProjects": [], "answerQuality": "average",
                    "confidence": "medium", "suggestedNextPhase": None}

    # Merge insights
    state["extractedSkills"] = list(dict.fromkeys(state["extractedSkills"] + insights["newSkills"]))
    state["extractedProjects"] = list(dict.fromkeys(state["extractedProjects"] + insights["newProjects"]))
    state["lastAnswerQuality"] = insights["answerQuality"]
    state["difficultyLevel"] = _next_difficulty(state["difficultyLevel"], insights["answerQuality"])
    if insights["suggestedNextPhase"]:
        state["phase"] = insights["suggestedNextPhase"]

    # Force wrap-up if we hit the cap
    if state["questionCount"] >= MAX_INTERVIEW_TURNS:
        state["phase"] = "wrap_up"

    # Step 2: generate next question (or closing message if wrap_up reached)
    try:
        next_question = await interview_next_question(
            client=http_client,
            provider=provider,
            api_key=api_key,
            model=model,
            state=state,
            resume_text=resume_text,
            history=history,
            profile=profile,
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except ProviderResponseError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Interview turn failed: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Interview turn failed: {str(error)}")

    history.append({"role": "assistant", "content": next_question})
    state["questionsAsked"].append(next_question)
    state["questionCount"] += 1

    # Mark complete if we just delivered the wrap-up message
    if state["phase"] == "wrap_up" and state["questionCount"] >= MAX_INTERVIEW_TURNS:
        state["completed"] = True

    section_map = {
        "introduction": "Introduction",
        "project_deep_dive": "Project Deep Dive",
        "skill_basic": "Core Skills",
        "skill_intermediate": "Intermediate",
        "skill_advanced": "Advanced",
        "wrap_up": "Wrap Up",
    }

    return {
        "question": next_question,
        "section": section_map.get(state["phase"], "Interview"),
        "state": state,
    }


@app.post("/api/interview/end")
async def interview_end(session_id: str = Form(...)):
    """Drop a session from the in-memory store."""
    INTERVIEW_SESSIONS.pop(session_id, None)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
