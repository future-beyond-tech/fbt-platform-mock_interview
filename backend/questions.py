"""
questions.py — Backward-compatibility shim.

Phase 4: The question catalogue has moved to features/questions/data.py.
This file re-exports everything so existing imports (main.py, evaluation router)
continue working without change.
"""

from features.questions.data import QUESTIONS, SESSIONS, _DAY_COUNTS as DAY_COUNTS

__all__ = ["QUESTIONS", "SESSIONS", "DAY_COUNTS"]
