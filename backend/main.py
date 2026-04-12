"""
FBT Mock Interviewer — Multi-provider FastAPI backend.
Supports: Ollama (local), Google Gemini, Groq, OpenAI, Anthropic.

Run:  uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import get_cors_origins, has_server_key
from shared.persistence.factory import make_session_store


def _log(*args, **kwargs):
    """Print with an ISO timestamp prefix. Preserves the caller's stream."""
    ts = datetime.now().isoformat(timespec="seconds")
    print(f"[{ts}]", *args, **kwargs)


# ── HTTP client (shared) ──
http_client: httpx.AsyncClient | None = None
# Phase 7: factory chooses SQLite vs Memory based on SESSION_STORE env var.
INTERVIEW_SESSION_STORE = make_session_store()


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
    # Expose shared resources on app.state so feature routers can access
    # them via `request.app.state.*` without global variables.
    app.state.http_client = http_client
    app.state.session_store = INTERVIEW_SESSION_STORE

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
    allow_origins=get_cors_origins(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# ── Feature routers (Phases 3–6) ──────────────────────────────────────────────
from features.evaluation.router import router as evaluation_router        # noqa: E402
from features.questions.router import router as questions_router          # noqa: E402
from features.transcription.router import router as transcription_router  # noqa: E402
from features.interview.router import router as interview_router          # noqa: E402

app.include_router(evaluation_router)
app.include_router(questions_router)
app.include_router(transcription_router)
app.include_router(interview_router)


# ── Core routes (health + providers) ─────────────────────────────────────────

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
            server_key_available=has_server_key("gemini"),
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
            server_key_available=has_server_key("groq"),
            default_model="llama-3.1-8b-instant",
            models=["llama-3.1-8b-instant", "qwen-qwq-32b", "gemma2-9b-it", "llama-3.3-70b-versatile"],
        ),
        ProviderInfo(
            id="openai",
            name="OpenAI",
            needs_key=True,
            server_key_available=has_server_key("openai"),
            default_model="gpt-4o-mini",
            models=["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1-nano"],
        ),
        ProviderInfo(
            id="anthropic",
            name="Anthropic",
            needs_key=True,
            server_key_available=has_server_key("anthropic"),
            default_model="claude-sonnet-4-20250514",
            models=["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"],
        ),
    ]
    return {"providers": providers}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
