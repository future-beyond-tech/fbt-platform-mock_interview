"""
session_store.py — Backward-compatibility shim.

Phase 7: The session store implementations have moved to shared/persistence/.
This file re-exports everything so existing imports continue working without change.
"""

from shared.persistence.ports import SessionStore
from shared.persistence.memory import MemorySessionStore
from shared.persistence.sqlite import SQLiteSessionStore

__all__ = ["SessionStore", "MemorySessionStore", "SQLiteSessionStore"]
