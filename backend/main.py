"""
FBT Mock Interviewer — Multi-provider FastAPI backend.
Supports: Ollama (local), Google Gemini, Groq, OpenAI, Anthropic.

Run:  uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
import os

from dotenv import load_dotenv


def _log(*args, **kwargs):
    """Print with an ISO timestamp prefix. Preserves the caller's stream."""
    ts = datetime.now().isoformat(timespec="seconds")
    print(f"[{ts}]", *args, **kwargs)

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
    CATEGORY_LABELS,
    ClientInputError,
    ProviderResponseError,
    clean_transcript,
    evaluate_with_provider,
    extract_interview_blueprint,
    extract_insights_from_answer,
    extract_profile_from_resume,
    generate_question_from_file,
    generate_questions_with_provider,
    generate_session_report,
    generate_structured_question,
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
    # LLM inference (especially blueprint extraction with large prompts and
    # up to 2048 output tokens) can legitimately take 30-90s depending on
    # provider load.  A too-tight read timeout causes the primary call to
    # fail *and* starves the fallback chain of time, producing cascading
    # ReadTimeout errors.  120s read gives a single call plenty of room
    # while the asyncio.wait_for wrapper in each endpoint still caps total
    # wall-clock time.
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(120.0, connect=10.0, read=120.0, write=10.0),
    )
    _log("[OK] FBT Mock backend ready - multi-provider mode")

    try:
        models = await _fetch_ollama_models()
        if models:
            _log(f"  Ollama connected - models: {models}")
        else:
            _log("  Ollama not running (optional - cloud providers still work)")
    except httpx.ConnectError:
        _log("  Ollama not running (optional - cloud providers still work)")

    yield
    await http_client.aclose()


app = FastAPI(title="FBT Mock API", lifespan=lifespan)
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
            default_model="gemma-3-27b-it",
            models=[
                "gemma-3-27b-it",
                "gemma-3-12b-it",
                "gemma-3-4b-it",
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-2.5-pro",
            ],
        ),
        ProviderInfo(
            id="groq",
            name="Groq",
            needs_key=True,
            server_key_available=_has_server_key("groq"),
            default_model="llama-3.1-8b-instant",
            models=["llama-3.1-8b-instant", "qwen-qwq-32b", "gemma2-9b-it", "llama-3.3-70b-versatile"],
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


class CleanTranscriptRequest(BaseModel):
    raw_transcript: str
    provider: str = "groq"
    api_key: str = ""
    model: str = ""


@app.post("/api/clean-transcript")
async def clean_transcript_endpoint(req: CleanTranscriptRequest):
    """Clean up a raw speech-to-text transcript via LLM."""
    if not req.raw_transcript.strip():
        return {"text": ""}

    try:
        cleaned = await clean_transcript(
            client=http_client,
            provider=req.provider,
            api_key=req.api_key,
            model=req.model,
            raw_transcript=req.raw_transcript,
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        # Non-fatal: return the raw transcript if cleanup fails.
        _log(f"[clean-transcript] cleanup failed: {error}")
        return {"text": req.raw_transcript}

    return {"text": cleaned}


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


# ── Interview (structured 12-question) ──
import uuid

INTERVIEW_SESSIONS: dict[str, dict] = {}
TOTAL_QUESTIONS = 12


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
    """Upload a resume PDF, extract blueprint, return Q1 (intro)."""
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

    # Extract the interview blueprint (rich profile + domain concepts).
    try:
        blueprint = await asyncio.wait_for(
            extract_interview_blueprint(
                client=http_client,
                provider=provider,
                api_key=api_key,
                model=chosen_model,
                resume_text=resume_text,
            ),
            timeout=180.0,
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except asyncio.TimeoutError:
        _log("[interview] blueprint extraction exceeded 180s timeout; using fallback")
        blueprint = None
    except Exception as error:
        _log(f"[interview] blueprint extraction failed: {type(error).__name__}: {error}; using fallback")
        blueprint = None

    if blueprint is None:
        blueprint = {
            "candidate_name": "Candidate",
            "primary_domain": "General Professional",
            "experience_years": 0,
            "seniority_level": "mid",
            "is_technical": True,
            "core_skills": [],
            "tools_and_technologies": [],
            "domain_core_concepts": [],
            "notable_projects": [],
            "career_summary": "",
            "behavioral_themes": [],
        }

    # Knowledge ladder is now embedded in the blueprint (single LLM call).
    ladder = blueprint.get("knowledge_ladder") or {
        "tier_1": {"level": "foundational", "label": "Foundations", "description": "", "topics": []},
        "tier_2": {"level": "advanced", "label": "Advanced", "description": "", "topics": []},
        "tier_3": {"level": "expert_practical", "label": "Expert", "description": "", "topics": []},
    }

    _log(f"[interview] blueprint: domain={blueprint['primary_domain']}, "
         f"seniority={blueprint['seniority_level']}, years={blueprint['experience_years']}, "
         f"t1_topics={len(ladder.get('tier_1', {}).get('topics', []))}, "
         f"t2_topics={len(ladder.get('tier_2', {}).get('topics', []))}, "
         f"t3_topics={len(ladder.get('tier_3', {}).get('topics', []))}")

    # Build a profile dict from the blueprint for backwards-compat with eval prompts.
    profile = {
        "domain": blueprint["primary_domain"],
        "roles": [blueprint.get("seniority_level", "mid") + " " + blueprint["primary_domain"]],
        "yearsOfExperience": blueprint["experience_years"],
        "experienceLevel": blueprint["seniority_level"],
        "isTechnical": blueprint.get("is_technical", True),
        "topSkills": blueprint.get("core_skills", []),
        "notableProjects": [p.get("name", "") for p in blueprint.get("notable_projects", [])],
    }

    # Q1 is always the fixed intro question.
    from providers import get_intro_question
    q1 = get_intro_question()

    session_state = {
        "questionCount": 1,
        "currentQuestionNumber": 1,
        "totalQuestions": TOTAL_QUESTIONS,
        "questionsAsked": [q1["question"]],
        "askedTopics": [q1["topic"]],
        "askedProjects": [],
        "tierCounters": {"tier_1": 0, "tier_2": 0, "tier_3": 0},
        "answers": [],
        "completed": False,
    }

    session_id = uuid.uuid4().hex
    INTERVIEW_SESSIONS[session_id] = {
        "resume_text": resume_text,
        "blueprint": blueprint,
        "ladder": ladder,
        "profile": profile,
        "state": session_state,
        "provider": provider,
        "model": chosen_model,
    }

    return {
        "session_id": session_id,
        "question": q1["question"],
        "category": q1["category"],
        "section": CATEGORY_LABELS.get(q1["category"], "Introduction"),
        "question_number": 1,
        "total_questions": TOTAL_QUESTIONS,
        "what_to_evaluate": q1["what_to_evaluate"],
        "state": session_state,
        "profile": profile,
        "blueprint": {
            "candidate_name": blueprint.get("candidate_name", "Candidate"),
            "primary_domain": blueprint["primary_domain"],
            "subject_specialization": blueprint.get("subject_specialization", ""),
            "role_type": blueprint.get("role_type", ""),
            "seniority_level": blueprint["seniority_level"],
            "experience_years": blueprint["experience_years"],
            "detection_reasoning": blueprint.get("detection_reasoning", ""),
        },
    }


@app.post("/api/interview/turn")
async def interview_turn(req: InterviewTurnRequest):
    """Submit answer to current Q, score it, return the next question."""
    session = INTERVIEW_SESSIONS.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found or expired.")

    answer = (req.answer or "").strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer is required.")

    state = session["state"]
    blueprint = session["blueprint"]
    profile = session.get("profile")
    provider = req.provider or session["provider"]
    model = req.model or session["model"]
    current_q_num = state["currentQuestionNumber"]

    # Record this answer.
    last_q = state["questionsAsked"][-1] if state["questionsAsked"] else ""
    state["answers"].append({
        "question": last_q,
        "answer": answer,
        "category": "",  # will be enriched below
        "score": None,
        "feedback": "",
    })

    # Generate the NEXT question.
    next_q_num = current_q_num + 1

    if next_q_num > TOTAL_QUESTIONS:
        state["completed"] = True
        return {
            "question": None,
            "category": "completed",
            "section": "Completed",
            "question_number": next_q_num,
            "total_questions": TOTAL_QUESTIONS,
            "what_to_evaluate": "",
            "state": state,
            "completed": True,
        }

    ladder = session.get("ladder")

    try:
        q_data = await generate_structured_question(
            client=http_client,
            provider=provider,
            api_key=req.api_key,
            model=model,
            blueprint=blueprint,
            question_number=next_q_num,
            total_questions=TOTAL_QUESTIONS,
            session_state=state,
            ladder=ladder,
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except ProviderResponseError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Question generation failed: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Question generation failed: {str(error)}")

    state["currentQuestionNumber"] = next_q_num
    state["questionCount"] = next_q_num
    state["questionsAsked"].append(q_data["question"])
    state["askedTopics"].append(q_data.get("topic", ""))

    # Track project names if project-based.
    if q_data.get("category") == "project_based" and q_data.get("topic"):
        state["askedProjects"].append(q_data["topic"])

    category = q_data.get("category", "domain_concept")
    section = CATEGORY_LABELS.get(category, category.replace("_", " ").title())

    return {
        "question": q_data["question"],
        "category": category,
        "section": section,
        "question_number": next_q_num,
        "total_questions": TOTAL_QUESTIONS,
        "what_to_evaluate": q_data.get("what_to_evaluate", ""),
        "difficulty": q_data.get("difficulty", "medium"),
        "state": state,
        "completed": False,
    }


class InterviewReportRequest(BaseModel):
    session_id: str
    provider: str = "gemini"
    api_key: str = ""
    model: str = ""
    answers: list[dict] = []  # Frontend answers with scores from Redux store


@app.post("/api/interview/report")
async def interview_report(req: InterviewReportRequest):
    """Generate the end-of-session performance report."""
    session = INTERVIEW_SESSIONS.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found or expired.")

    blueprint = session["blueprint"]
    # Prefer frontend answers (they have scores from /api/evaluate).
    # Backend answers only have question+answer, no scores.
    answers = req.answers if req.answers else session["state"].get("answers", [])
    provider = req.provider or session["provider"]
    model = req.model or session["model"]

    try:
        report = await generate_session_report(
            client=http_client,
            provider=provider,
            api_key=req.api_key,
            model=model,
            blueprint=blueprint,
            answers=answers,
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        _log(f"[interview] report generation failed: {error}")
        raise HTTPException(status_code=502, detail=f"Report generation failed: {str(error)}")

    return {"report": report}


@app.post("/api/interview/end")
async def interview_end(session_id: str = Form(...)):
    """Drop a session from the in-memory store."""
    INTERVIEW_SESSIONS.pop(session_id, None)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
