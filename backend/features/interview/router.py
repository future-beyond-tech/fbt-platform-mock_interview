"""features/interview/router.py — FastAPI router for interview session endpoints.

Moves POST /api/interview/start, /api/interview/enqueue-probe,
/api/interview/turn, /api/interview/report, /api/interview/end,
and POST /api/generate-from-file out of main.py.
Zero API contract changes.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from providers import (
    CATEGORY_LABELS,
    ClientInputError,
    ProviderResponseError,
    extract_interview_blueprint,
    generate_followup_question_with_provider,
    generate_question_from_file,
    generate_session_report,
    generate_structured_question,
    get_intro_question,
)
from providers import _extract_pdf_text  # noqa: PLC2701 — internal helper reused

from shared.interview_utils import (
    _answer_question_index,
    _build_interview_answer_record,
    _sorted_interview_answers,
    _upsert_interview_answer,
)

from features.interview.models import (
    EnqueueProbeRequest,
    InterviewReportRequest,
    InterviewTurnRequest,
)

router = APIRouter(prefix="/api", tags=["interview"])

# 12 structured blueprint questions + up to 2 extra probing questions (tier 1–3 partials).
BLUEPRINT_QUESTION_COUNT = 12
MAX_SESSION_QUESTIONS = 14

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


def _log(*args, **kwargs):
    """Print with an ISO timestamp prefix."""
    ts = datetime.now().isoformat(timespec="seconds")
    print(f"[{ts}]", *args, **kwargs)


def _http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def _session_store(request: Request):
    return request.app.state.session_store


def _http_error_detail(error: httpx.HTTPStatusError) -> str:
    body = error.response.text[:200] if error.response is not None else str(error)
    return body or str(error)


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


@router.post("/generate-from-file")
async def generate_from_file(
    request: Request,
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
            client=_http_client(request),
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


@router.post("/interview/start")
async def interview_start(
    request: Request,
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
    client = _http_client(request)
    store = _session_store(request)

    # Extract the interview blueprint (rich profile + domain concepts).
    try:
        blueprint = await asyncio.wait_for(
            extract_interview_blueprint(
                client=client,
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
    q1 = get_intro_question()

    session_state = {
        "questionCount": 1,
        "currentQuestionNumber": 1,
        "totalQuestions": MAX_SESSION_QUESTIONS,
        "questionsAsked": [q1["question"]],
        "askedTopics": [q1["topic"]],
        "askedProjects": [],
        "tierCounters": {"tier_1": 0, "tier_2": 0, "tier_3": 0},
        "answers": [],
        "completed": False,
        "next_blueprint_qnum": 2,
        "dynamic_queue": [],
        "dynamic_slots_used": 0,
        "current_question_category": q1["category"],
    }

    session_id = uuid.uuid4().hex
    session_payload = {
        "resume_text": resume_text,
        "blueprint": blueprint,
        "ladder": ladder,
        "profile": profile,
        "state": session_state,
        "provider": provider,
        "model": chosen_model,
    }
    store.set(session_id, session_payload)

    return {
        "session_id": session_id,
        "question": q1["question"],
        "category": q1["category"],
        "section": CATEGORY_LABELS.get(q1["category"], "Introduction"),
        "question_number": 1,
        "total_questions": MAX_SESSION_QUESTIONS,
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


@router.post("/interview/enqueue-probe")
async def interview_enqueue_probe(req: EnqueueProbeRequest, request: Request):
    """Queue one extra probing question (max 2 per session); only tier_1–tier_3 categories."""
    store = _session_store(request)
    session = store.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found or expired.")

    cat = (req.category or "").strip()
    if cat not in ("tier_1", "tier_2", "tier_3"):
        raise HTTPException(status_code=400, detail="Probing questions apply only to tier 1, 2, or 3.")

    state = session["state"]
    if state.get("dynamic_slots_used", 0) >= 2:
        raise HTTPException(status_code=400, detail="Maximum extra questions for this session reached.")

    oq = (req.original_question or "").strip()
    ua = (req.user_answer or "").strip()
    if not oq or not ua:
        raise HTTPException(status_code=400, detail="original_question and user_answer are required.")

    provider = req.provider or session["provider"]
    model = req.model or session["model"]

    try:
        text = await generate_followup_question_with_provider(
            client=_http_client(request),
            provider=provider,
            api_key=req.api_key,
            model=model,
            original_question=oq,
            user_answer=ua,
            topic=cat,
            profile=session.get("profile"),
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except ProviderResponseError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Cannot reach the provider. Is Ollama running?" if provider == "ollama"
            else "Cannot reach the provider API.",
        )
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Provider error: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Provider error: {str(error)}")

    q_item = {
        "question": text,
        "topic": cat,
        "category": cat,
        "what_to_evaluate": "Clarifies a specific claim or example from the candidate's previous answer.",
        "difficulty": "medium",
    }
    state.setdefault("dynamic_queue", []).append(q_item)
    state["dynamic_slots_used"] = state.get("dynamic_slots_used", 0) + 1
    store.set(req.session_id, session)

    return {
        "queued": True,
        "dynamic_slots_used": state["dynamic_slots_used"],
        "state": state,
    }


@router.post("/interview/turn")
async def interview_turn(req: InterviewTurnRequest, request: Request):
    """Submit answer to current Q, return the next question (blueprint or queued probe)."""
    store = _session_store(request)
    session = store.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found or expired.")

    answer = (req.answer or "").strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer is required.")

    state = session["state"]
    blueprint = session["blueprint"]
    provider = req.provider or session["provider"]
    model = req.model or session["model"]
    current_q_num = state["currentQuestionNumber"]

    last_q = state["questionsAsked"][-1] if state["questionsAsked"] else ""
    answered_category = state.get("current_question_category", "")
    current_section = CATEGORY_LABELS.get(answered_category, answered_category.replace("_", " ").title())
    existing_answer = next(
        (item for item in state.get("answers", []) if _answer_question_index(item) == current_q_num),
        None,
    )
    if existing_answer is None or existing_answer.get("answer") != answer or existing_answer.get("question") != last_q:
        _upsert_interview_answer(
            state,
            _build_interview_answer_record(
                question_number=current_q_num,
                question_text=last_q,
                answer_text=answer,
                category=answered_category,
                section_text=current_section,
            ),
        )
        store.set(req.session_id, session)

    ladder = session.get("ladder")
    next_display_num = current_q_num + 1
    dq = state.get("dynamic_queue") or []

    # Serve a queued probing question next (same UI as any other question).
    if dq:
        q_item = dq.pop(0)
        state["dynamic_queue"] = dq
        state["currentQuestionNumber"] = next_display_num
        state["questionCount"] = next_display_num
        state["questionsAsked"].append(q_item["question"])
        state["askedTopics"].append(q_item.get("topic", ""))
        cat = q_item.get("category", "tier_1")
        state["current_question_category"] = cat
        section = CATEGORY_LABELS.get(cat, cat.replace("_", " ").title())
        store.set(req.session_id, session)
        return {
            "question": q_item["question"],
            "category": cat,
            "section": section,
            "question_number": next_display_num,
            "total_questions": MAX_SESSION_QUESTIONS,
            "what_to_evaluate": q_item.get("what_to_evaluate", ""),
            "difficulty": q_item.get("difficulty", "medium"),
            "state": state,
            "completed": False,
        }

    nb = state.get("next_blueprint_qnum", 2)

    if nb > BLUEPRINT_QUESTION_COUNT:
        state["completed"] = True
        store.set(req.session_id, session)
        return {
            "question": None,
            "category": "completed",
            "section": "Completed",
            "question_number": next_display_num,
            "total_questions": MAX_SESSION_QUESTIONS,
            "what_to_evaluate": "",
            "state": state,
            "completed": True,
        }

    if next_display_num > MAX_SESSION_QUESTIONS:
        state["completed"] = True
        store.set(req.session_id, session)
        return {
            "question": None,
            "category": "completed",
            "section": "Completed",
            "question_number": next_display_num,
            "total_questions": MAX_SESSION_QUESTIONS,
            "what_to_evaluate": "",
            "state": state,
            "completed": True,
        }

    try:
        q_data = await generate_structured_question(
            client=_http_client(request),
            provider=provider,
            api_key=req.api_key,
            model=model,
            blueprint=blueprint,
            question_number=nb,
            total_questions=BLUEPRINT_QUESTION_COUNT,
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

    state["next_blueprint_qnum"] = nb + 1
    state["currentQuestionNumber"] = next_display_num
    state["questionCount"] = next_display_num
    state["questionsAsked"].append(q_data["question"])
    state["askedTopics"].append(q_data.get("topic", ""))

    if q_data.get("category") == "project_based" and q_data.get("topic"):
        state["askedProjects"].append(q_data["topic"])

    category = q_data.get("category", "domain_concept")
    state["current_question_category"] = category
    section = CATEGORY_LABELS.get(category, category.replace("_", " ").title())
    store.set(req.session_id, session)

    return {
        "question": q_data["question"],
        "category": category,
        "section": section,
        "question_number": next_display_num,
        "total_questions": MAX_SESSION_QUESTIONS,
        "what_to_evaluate": q_data.get("what_to_evaluate", ""),
        "difficulty": q_data.get("difficulty", "medium"),
        "state": state,
        "completed": False,
    }


@router.post("/interview/report")
async def interview_report(req: InterviewReportRequest, request: Request):
    """Generate the end-of-session performance report."""
    store = _session_store(request)
    session = store.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Interview session not found or expired.")

    blueprint = session["blueprint"]
    answers = _sorted_interview_answers(session.get("state") or {})
    provider = req.provider or session["provider"]
    model = req.model or session["model"]

    try:
        report = await generate_session_report(
            client=_http_client(request),
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

    return {"report": report, "answers": answers}


@router.post("/interview/end")
async def interview_end(request: Request, session_id: str = Form(...)):
    """Drop a session from the persisted store."""
    _session_store(request).delete(session_id)
    return {"ok": True}
