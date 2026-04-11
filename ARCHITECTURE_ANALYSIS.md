# InterVu — Architecture Analysis & Recommendation

**Date:** April 10, 2026  
**Project:** InterVu Simulator  
**Stack:** React 19 (Vite) + FastAPI (Python) + Multi-Provider LLM

---

## Part 1: Current Architecture — What You Have

### Pattern Identified: **Monolithic Architecture** with elements of **Layered (N-Tier)**

Your project follows a **two-tier monolith** pattern — a single React frontend process talks to a single FastAPI backend process, which holds all business logic, session state, and external integrations in one deployable unit.

```
┌─────────────────────────────────┐
│         React Frontend          │
│  (App.jsx = central state       │
│   machine controlling all       │
│   phases and screens)           │
└──────────────┬──────────────────┘
               │  HTTP (Vite proxy)
┌──────────────▼──────────────────┐
│        FastAPI Backend          │
│  ┌────────────────────────────┐ │
│  │  main.py (routes + state   │ │
│  │  + validation + sessions)  │ │
│  ├────────────────────────────┤ │
│  │  providers.py (LLM calls   │ │
│  │  + retry + circuit breaker │ │
│  │  + prompt engineering +    │ │
│  │  PDF extraction + scoring) │ │
│  ├────────────────────────────┤ │
│  │  questions.py (static data)│ │
│  └────────────────────────────┘ │
└──────────────┬──────────────────┘
               │  HTTP
┌──────────────▼──────────────────┐
│   External LLM APIs             │
│   (Ollama/Groq/Gemini/          │
│    OpenAI/Anthropic)            │
└─────────────────────────────────┘
```

### Specific Patterns Present

**Frontend:**
- **State Machine in App.jsx** — One giant `useState` object controls all phases (`start`, `question`, `thinking`, `result`, `done`, `interview`). Every screen reads from and writes to this single state atom.
- **No state management library** — Pure React hooks, no Redux/Zustand/Context.
- **Lazy loading** — Good use of `React.lazy()` for code splitting.
- **Thin API layer** — `api.js` is a procedural fetch wrapper with no caching, deduplication, or optimistic updates.

**Backend:**
- **God file pattern** — `main.py` (750 lines) handles routing, request validation, session management, error mapping, and orchestration all in one file.
- **God file pattern** — `providers.py` (estimated 1500+ lines) combines LLM abstraction, retry logic, circuit breaking, prompt engineering, PDF parsing, scoring logic, and blueprint extraction.
- **In-memory session store** — `INTERVIEW_SESSIONS` dict holds all live interview state. Lost on restart. No persistence.
- **No service layer** — Route handlers directly call provider functions, mixing HTTP concerns with business logic.
- **No repository/data access layer** — Static question data, session state, and external API calls all happen at the same level.

---

## Part 2: Strengths of Current Architecture

| Strength | Details |
|----------|---------|
| **Simple to run** | Two commands: `uvicorn` + `npm run dev`. No infrastructure. |
| **Fast iteration** | Everything in one place, easy to find and change. |
| **Good resilience patterns** | Retry with exponential backoff, circuit breaker, provider fallback — production-quality. |
| **Clean API boundary** | Frontend and backend communicate only through a well-defined REST API. |
| **Lazy loading** | React.lazy() for code splitting is a good performance practice. |
| **Multi-provider abstraction** | Switching LLM providers is seamless — good adapter pattern. |

---

## Part 3: Problems & Pain Points

### Critical Issues

| Problem | Impact | Where |
|---------|--------|-------|
| **In-memory sessions** | All interview state lost on server restart. No horizontal scaling possible. | `main.py:469` — `INTERVIEW_SESSIONS: dict` |
| **providers.py is a monolith** | 1500+ lines mixing 6 concerns: LLM calls, retries, prompts, PDF parsing, scoring, blueprint extraction. Hard to test, hard to extend. | `providers.py` |
| **No persistence layer** | Can't save interview history, user progress, analytics. Everything is ephemeral. | Entire backend |
| **Frontend state blob** | Single `useState` with 15+ fields. Adding features means touching one massive state object. | `App.jsx:29-48` |
| **No error boundaries** | A crash in any component takes down the entire app. | Frontend-wide |
| **API keys in frontend** | Users pass API keys through the browser. No server-side key management. | `useSettings.js` + every API call |

### Moderate Issues

| Problem | Impact |
|---------|--------|
| **No TypeScript** | No compile-time safety on either frontend or backend models. Mismatched field names caught only at runtime. |
| **No testing on frontend** | Only `test_backend.py` exists. Zero frontend tests. |
| **Duplicated question data** | `questions.py` (backend) + `data/questions.js` (frontend) — two sources of truth. |
| **No request caching** | Every page load re-fetches questions and providers. No SWR/React Query. |
| **Logging but no observability** | `_log()` prints to stdout. No structured logging, metrics, or tracing. |

---

## Part 4: Recommended Architecture

### **Modular Monolith + Vertical Slice Architecture**

For a project of this size and team (likely 1-3 developers), jumping to microservices would be over-engineering. Instead, I recommend restructuring into a **Modular Monolith** where the backend is organized by **feature slices** (not technical layers), combined with a **Hexagonal (Ports & Adapters)** pattern for the LLM integration layer.

This gives you the organizational clarity of microservices with the operational simplicity of a monolith — and a clean extraction path if you ever need to split.

### Why NOT Microservices

- You have one database (none, actually — you need to add one)
- You have one team
- The features are tightly coupled (interview needs evaluation, evaluation needs providers, providers need prompts)
- Deployment complexity would 10x for marginal benefit

### Why NOT Pure Layered Architecture

- Your business logic doesn't map cleanly to horizontal layers
- "Services" and "repositories" for a project this size create busywork
- Vertical slices keep related code together, making features easier to reason about

---

## Part 5: Proposed Project Structure

```
sheikh-mock/
├── backend/
│   ├── app.py                        # FastAPI app factory + middleware
│   ├── config.py                     # All configuration, env vars
│   ├── shared/
│   │   ├── llm/
│   │   │   ├── __init__.py
│   │   │   ├── ports.py              # Abstract LLMProvider interface
│   │   │   ├── adapters/
│   │   │   │   ├── ollama.py         # Ollama adapter
│   │   │   │   ├── groq.py           # Groq adapter
│   │   │   │   ├── gemini.py         # Gemini adapter
│   │   │   │   ├── openai.py         # OpenAI adapter
│   │   │   │   └── anthropic.py      # Anthropic adapter
│   │   │   ├── resilience.py         # Retry, circuit breaker, fallback
│   │   │   └── registry.py           # Provider registry + factory
│   │   ├── pdf.py                    # PDF text extraction
│   │   └── persistence/
│   │       ├── ports.py              # Abstract SessionStore interface
│   │       ├── memory.py             # In-memory (dev)
│   │       └── sqlite.py             # SQLite (production)
│   │
│   ├── features/
│   │   ├── evaluation/               # ── Vertical Slice: Answer Evaluation
│   │   │   ├── router.py             # POST /api/evaluate
│   │   │   ├── service.py            # Scoring logic + prompt engineering
│   │   │   ├── models.py             # EvalRequest, EvalResult
│   │   │   └── prompts.py            # Evaluation prompt templates
│   │   │
│   │   ├── questions/                # ── Vertical Slice: Question Bank
│   │   │   ├── router.py             # GET /api/questions, POST /api/generate-questions
│   │   │   ├── service.py            # Question generation logic
│   │   │   ├── data.py               # Static 68-question catalogue
│   │   │   └── models.py             # Question schemas
│   │   │
│   │   ├── interview/                # ── Vertical Slice: Structured Interview
│   │   │   ├── router.py             # /api/interview/* endpoints
│   │   │   ├── service.py            # Session management, blueprint, progression
│   │   │   ├── models.py             # InterviewSession, Blueprint, etc.
│   │   │   └── prompts.py            # Interview-specific prompts
│   │   │
│   │   ├── transcription/            # ── Vertical Slice: Voice
│   │   │   ├── router.py             # POST /api/transcribe, /api/clean-transcript
│   │   │   └── service.py            # Whisper integration
│   │   │
│   │   └── providers/                # ── Vertical Slice: Provider Config
│   │       ├── router.py             # GET /api/providers, GET /api/health
│   │       └── models.py             # ProviderInfo schema
│   │
│   ├── tests/
│   │   ├── test_evaluation.py
│   │   ├── test_interview.py
│   │   ├── test_questions.py
│   │   └── test_llm_adapters.py
│   │
│   └── main.py                       # Entrypoint (imports app from app.py)
│
├── src/
│   ├── App.jsx                       # Thin shell — routes only
│   ├── api/
│   │   ├── client.js                 # Base fetch with error handling
│   │   ├── evaluation.js             # Evaluation API calls
│   │   ├── questions.js              # Question API calls
│   │   ├── interview.js              # Interview API calls
│   │   └── transcription.js          # Voice API calls
│   ├── stores/
│   │   ├── useInterviewStore.js      # Interview-specific state (Zustand)
│   │   ├── useSessionStore.js        # Question session state
│   │   └── useSettingsStore.js       # Provider settings (persisted)
│   ├── features/
│   │   ├── interview/                # Interview mode components
│   │   ├── session/                  # Standard Q&A components
│   │   ├── upload/                   # File upload flow
│   │   └── results/                  # Score + report views
│   ├── components/ui/                # Shared UI primitives
│   └── hooks/                        # Shared hooks (useVoice, useTypewriter)
```

---

## Part 6: Key Architectural Changes

### 1. Hexagonal Architecture for LLM Layer (Ports & Adapters)

**Before:** One 1500-line file with all providers inlined.

**After:** An abstract `LLMProvider` interface (port) with separate adapter files per provider.

```python
# shared/llm/ports.py — THE CONTRACT
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, model: str) -> str: ...

    @abstractmethod
    async def complete_json(self, prompt: str, model: str, schema: dict) -> dict: ...
```

```python
# shared/llm/adapters/groq.py — ONE ADAPTER
class GroqProvider(LLMProvider):
    async def complete(self, prompt, model):
        # Groq-specific HTTP call
        ...
```

**Why:** Adding a new LLM provider = adding one file. Testing = mock the port. No provider code touches another.

### 2. Feature-Based Vertical Slices (Backend)

**Before:** All routes in `main.py`, all logic in `providers.py`.

**After:** Each feature owns its routes, models, service logic, and prompts.

The interview feature doesn't know how evaluation prompts work. The evaluation feature doesn't know about session progression. They share only the LLM port and the persistence port.

### 3. Persistent Session Store

**Before:** `INTERVIEW_SESSIONS: dict = {}` — volatile.

**After:** Abstract `SessionStore` port with `MemoryStore` (dev) and `SQLiteStore` (prod).

```python
# shared/persistence/ports.py
class SessionStore(ABC):
    @abstractmethod
    async def save(self, session_id: str, data: dict) -> None: ...

    @abstractmethod
    async def load(self, session_id: str) -> dict | None: ...

    @abstractmethod
    async def delete(self, session_id: str) -> None: ...
```

SQLite requires zero infrastructure and gives you persistence, history, and analytics for free.

### 4. Decomposed Frontend State

**Before:** One `useState` with 15 fields in App.jsx.

**After:** Feature-specific stores using Zustand (2KB, no boilerplate).

```javascript
// stores/useInterviewStore.js
export const useInterviewStore = create((set) => ({
  sessionId: null,
  question: null,
  questionNumber: 0,
  answers: [],
  submitAnswer: async (answer) => { ... },
  nextQuestion: async () => { ... },
}));
```

Each feature manages its own state. App.jsx becomes a thin router.

### 5. Error Boundaries

Wrap each feature in a React Error Boundary so a crash in the interview flow doesn't kill the question bank.

---

## Part 7: Migration Plan (Incremental, Non-Breaking)

The beauty of vertical slices is you can migrate one feature at a time. Here's the order, designed so nothing breaks between steps:

| Phase | What | Effort | Risk |
|-------|------|--------|------|
| **1** | Extract `config.py` from scattered env vars and constants | 1 hour | None |
| **2** | Extract LLM adapters from `providers.py` into `shared/llm/` | 3-4 hours | Low — pure refactor |
| **3** | Extract `features/evaluation/` (routes + service + models) | 2 hours | Low |
| **4** | Extract `features/questions/` | 1 hour | Low |
| **5** | Extract `features/transcription/` | 1 hour | Low |
| **6** | Extract `features/interview/` (most complex) | 3 hours | Medium |
| **7** | Add `shared/persistence/` with SQLite session store | 2-3 hours | Medium |
| **8** | Frontend: split `api.js` into feature modules | 1 hour | Low |
| **9** | Frontend: introduce Zustand stores per feature | 3-4 hours | Medium |
| **10** | Frontend: add Error Boundaries | 1 hour | None |

**Total estimated effort:** 18-22 hours of focused work, spread across 1-2 weeks.

Each phase is independently deployable. You can stop after any phase and still have a working app.

---

## Part 8: Architecture Comparison

| Criterion | Current (Monolith) | Recommended (Modular Monolith) | Microservices (Overkill) |
|-----------|-------------------|-------------------------------|-------------------------|
| **Complexity** | Low | Medium | High |
| **Deployment** | 2 commands | 2 commands | Docker + orchestrator |
| **Testability** | Hard (god files) | Easy (isolated slices) | Easy but complex setup |
| **Scalability** | Vertical only | Vertical + easy extraction | Horizontal |
| **New feature cost** | Modify 2-3 big files | Add a new slice folder | New service + infra |
| **Team size fit** | 1-2 devs | 1-5 devs | 5+ devs |
| **Persistence** | None | SQLite (upgradeable) | Per-service DBs |
| **LLM provider addition** | Edit 1500-line file | Add 1 adapter file | Add 1 adapter file |

---

## Part 9: What to Do First

If you only do three things, do these:

1. **Extract the LLM adapters** — This immediately makes `providers.py` manageable and testable. One file per provider, one shared interface.

2. **Add SQLite persistence** — Replace `INTERVIEW_SESSIONS: dict` with a proper store. This unlocks interview history, analytics, and server restarts without data loss.

3. **Split frontend state** — Move from one `useState` blob to Zustand stores per feature. This makes each screen's logic self-contained.

Everything else is refinement on top of these three moves.

---

*This analysis is based on the codebase as of April 10, 2026. The recommendations prioritize pragmatic improvements that match the project's current scale while creating a clean path for growth.*
