# FBT Mock — Project Architecture

This document describes the **current** layout of the **sheikh-mock** codebase: the React/Vite frontend, the FastAPI backend, shared abstractions, and how data flows between them.

---

## High-level system

```text
Browser (React + Vite, :5173)
    │  fetch /api/*  (same-origin via Vite proxy, or VITE_API_URL)
    ▼
FastAPI (backend/main.py, :8000)
    ├── Feature routers (interview, questions, evaluation, transcription)
    ├── Core routes (health, providers)
    └── Shared: httpx client, session store, LLM registry → providers
```

- **Frontend** talks to the backend over HTTP JSON and multipart uploads.
- **Vite** proxies `/api` to `http://localhost:8000` in development (`vite.config.js`).
- **Production / custom hosts**: set `VITE_API_URL` on the client to the API origin.

---

## Repository layout

| Area | Path | Role |
|------|------|------|
| Frontend app | `src/` | React UI, state, API clients |
| Backend app | `backend/` | FastAPI, features, legacy orchestration |
| Tests | `tests/` | Backend tests (e.g. `test_backend.py`) |
| Static / tooling | `index.html`, `vite.config.js`, `eslint.config.js`, `lighthouserc.json` | Build, lint, quality |

---

## Frontend architecture

### Stack

- **React 19** with **Vite 6**
- **Zustand** (`useSessionStore`) for interview flow UI state (phase, loading, practice session, AI interview session handle)
- **Redux Toolkit** for interview-specific slice data (`interviewSlice` — blueprint, question list) used when driving the full AI interview path
- **react-redux** to dispatch from `App.jsx`

### Entry and routing (by phase, not React Router)

- `src/main.jsx` mounts the app.
- `src/App.jsx` is the **phase router**: `start` → upload, `interview` → `InterviewSession`, practice modes (`question` / `thinking` / `result`) → `SessionScreen`, `done` → `DoneScreen`.
- Heavy UI is **lazy-loaded** (`Particles`, `SettingsDrawer`, `SessionScreen`, `DoneScreen`, `InterviewSession`) behind `Suspense`.

### API layer

- `src/api/client.js` — `BASE` (`VITE_API_URL || ''`) and `extractErrorDetail`.
- Feature modules: `interview.js`, `questions.js`, `evaluation.js`, `transcription.js`.
- `src/api/index.js` re-exports everything plus `fetchProviders` and `healthCheck`.
- `src/api.js` may still exist for backward compatibility; prefer `src/api/` for new code.

### Components and UI

- `src/components/` — screens (`UploadPage`, `SessionScreen`, `InterviewSession`, …) and feature widgets.
- `src/components/ui/` — reusable primitives (`Button`, `Card`, `Alert`, …).

### Other frontend folders

- `src/hooks/` — e.g. voice, typewriter, settings.
- `src/store/` — Zustand stores and Redux slice/selectors.
- `src/data/questions.js` — static/question data where used on the client.

---

## Backend architecture

### Entry point

- `backend/main.py` defines the **FastAPI** app, **lifespan** (creates shared `httpx.AsyncClient`, attaches `app.state.http_client` and `app.state.session_store`), **CORS**, and mounts feature routers. It also exposes:
  - `GET /api/health` — process + optional Ollama model probe
  - `GET /api/providers` — provider metadata, models, and whether server-side keys exist

### Configuration

- `backend/config.py` — **pydantic-settings** `Settings` singleton (`settings`), loaded from `backend/.env` then project-root `.env` (project wins where overlapping).
- Notable settings: API keys, `ollama_base_url`, `default_provider`, `session_store` (`memory` | `sqlite`), `sqlite_db_path`, `max_interview_sessions`, `backend_cors_origins`.
- Helpers: `get_cors_origins()`, `has_server_key()`, `get_config_value()` (used by older call sites).

### Feature modules (`backend/features/`)

Each feature is a **vertical slice**: router (+ models/service where applicable).

| Feature | Router prefix | Responsibility |
|---------|----------------|----------------|
| **interview** | `/api` | Resume PDF upload, blueprint extraction, session lifecycle (`/interview/start`, `/interview/turn`, `/interview/enqueue-probe`, `/interview/report`, `/interview/end`), file → single question (`/generate-from-file`) |
| **questions** | `/api` | `GET /questions`, `POST /generate-questions` |
| **evaluation** | `/api` | `POST /evaluate`, `/generate-followup`, `/evaluate-followup` |
| **transcription** | `/api` | `POST /transcribe` (Groq Whisper), `POST /clean-transcript` |

Routers read `request.app.state.http_client` and `request.app.state.session_store` instead of relying on globals (except where legacy modules are imported).

### Shared layers (`backend/shared/`)

- **`shared/persistence/`**
  - `ports.py` — `SessionStore` protocol (`get` / `set` / `delete`)
  - `memory.py`, `sqlite.py` — implementations
  - `factory.py` — `make_session_store()` from `SESSION_STORE` / `settings.session_store`
- **`shared/llm/`**
  - `ports.py` — abstract `LLMProvider.chat(...)` + `is_available`
  - `adapters/` — Ollama, Gemini, Groq, OpenAI, Anthropic
  - `registry.py` — `get_provider(name)` singleton adapters
  - `resilience.py` — retries, cooldowns, shared HTTP stress handling used from `providers.py`
- **`shared/interview_utils.py`** — normalizing and upserting answer records into session state (used by interview + evaluation paths)

### Legacy orchestration (still central)

- **`backend/providers.py`** — Large module that remains the **orchestration layer** for LLM calls: prompt construction, blueprint extraction, structured questions, reports, evaluation, follow-ups, file-based question generation, etc. It delegates low-level HTTP chat to **`shared.llm.registry`** and uses **`shared.llm.resilience`**.
- **`backend/questions.py`** — Canonical question list / IDs for practice mode; evaluation router resolves `question_id` via this module.

### Session storage

- Interview sessions are keyed by `session_id` (hex UUID) and hold blueprint, ladder, profile, provider/model, and mutable `state` (questions asked, answers, queues, completion).
- **Memory**: ephemeral per process.
- **SQLite**: persistent path from `SQLITE_DB_PATH` / settings (runtime files may appear under `backend/.runtime/` in dev).

---

## Primary API surface (reference)

Paths are relative to the API root (e.g. `/api/...`).

**Core**

- `GET /api/health`
- `GET /api/providers`

**Interview**

- `POST /api/interview/start` — multipart: PDF resume + provider fields
- `POST /api/interview/turn` — JSON: answer + session id
- `POST /api/interview/enqueue-probe` — JSON: probe metadata
- `POST /api/interview/report` — JSON: session id
- `POST /api/interview/end` — form: session id
- `POST /api/generate-from-file` — multipart: image/PDF → one question

**Questions**

- `GET /api/questions`
- `POST /api/generate-questions`

**Evaluation**

- `POST /api/evaluate`
- `POST /api/generate-followup`
- `POST /api/evaluate-followup`

**Transcription**

- `POST /api/transcribe` — audio upload (Groq)
- `POST /api/clean-transcript` — JSON: raw text cleanup via LLM

---

## Request flow examples

1. **Practice mode (fixed question bank)**  
   Frontend loads `GET /api/questions` and `GET /api/providers`. User answers; client may call `POST /api/clean-transcript` then `POST /api/evaluate` with `question_id` (and optionally `interview_session_id` if tied to a stored session).

2. **Full AI interview (resume-driven)**  
   User uploads PDF → `POST /api/interview/start` stores session and returns Q1. Each answer → `POST /api/interview/turn`. Optional probes → `POST /api/interview/enqueue-probe`. End → `POST /api/interview/report`, then `POST /api/interview/end` to delete server session.

3. **LLM provider selection**  
   UI sends `provider`, optional per-request `api_key`, and `model`. Server merges with env-configured keys via `resolve_api_key` / settings. Adapters in `shared/llm/adapters/` perform provider-specific HTTP.

---

## Dependencies (summary)

**Python** (`backend/requirements.txt`): FastAPI, uvicorn, httpx, pydantic / pydantic-settings, python-multipart, pypdf, Pillow, python-dotenv.

**Node** (`package.json`): react, react-dom, @reduxjs/toolkit, react-redux, zustand; Vite + ESLint for dev.

---

## Conventions

- **API contract**: Feature routers were extracted from `main.py` with an explicit goal of **no breaking changes** to existing paths and payloads.
- **Errors**: Routers map `ClientInputError` → 400, `ProviderResponseError` → 422, HTTP/upstream issues → 502/503 as appropriate.
- **Security note**: API keys from the UI are sent to **your** backend only; treat deployment TLS and CORS (`backend_cors_origins`) as part of your threat model.

---

*Generated to reflect the structure of the repository as of the document date; adjust this file when you add new features or move boundaries between layers.*
