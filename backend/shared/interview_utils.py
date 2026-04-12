"""
shared/interview_utils.py — Pure helper functions for interview session state.

These are shared between the evaluation router (which updates answers during
evaluation) and the future interview router (Phase 6).  They contain zero
I/O and zero imports from feature modules — just data manipulation.
"""

from __future__ import annotations


def answer_question_index(answer: dict) -> int:
    raw = answer.get("questionIndex", answer.get("question_number", 0))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def sorted_interview_answers(state: dict) -> list[dict]:
    return sorted(list(state.get("answers", [])), key=answer_question_index)


def upsert_interview_answer(state: dict, answer_record: dict) -> None:
    """Insert or replace an answer in *state['answers']*, keyed by question index."""
    answers = state.setdefault("answers", [])
    question_index = answer_question_index(answer_record)

    for idx, existing in enumerate(answers):
        if answer_question_index(existing) == question_index:
            answers[idx] = answer_record
            return

    answers.append(answer_record)
    answers.sort(key=answer_question_index)


def build_interview_answer_record(
    *,
    question_number: int,
    question_text: str,
    answer_text: str,
    category: str,
    section_text: str,
    result: dict | None = None,
) -> dict:
    """Build the standard answer record that gets stored in interview session state."""
    payload = result or {}
    gaps = payload.get("gaps") if isinstance(payload.get("gaps"), list) else []

    return {
        "questionIndex": question_number,
        "question_number": question_number,
        "question": question_text,
        "answer": answer_text,
        "score": payload.get("score"),
        "verdict": payload.get("verdict", ""),
        "strength": payload.get("strength", ""),
        "missing": payload.get("missing", ""),
        "gaps": gaps,
        "hint": payload.get("hint", ""),
        "ideal": payload.get("ideal", ""),
        "category": category,
        "section": section_text,
        "feedback": payload.get("strength", ""),
    }


# ── Backward-compatible aliases (main.py uses these private names) ────────────
_answer_question_index = answer_question_index
_sorted_interview_answers = sorted_interview_answers
_upsert_interview_answer = upsert_interview_answer
_build_interview_answer_record = build_interview_answer_record
