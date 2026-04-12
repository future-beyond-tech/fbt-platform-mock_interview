"""shared/persistence/factory.py — Config-driven store factory.

Usage:
    from shared.persistence.factory import make_session_store
    store = make_session_store()          # reads settings.session_store
    store = make_session_store("memory")  # force in-memory
    store = make_session_store("sqlite")  # force SQLite
"""

from __future__ import annotations

from config import settings
from shared.persistence.memory import MemorySessionStore
from shared.persistence.sqlite import SQLiteSessionStore


def make_session_store(backend: str | None = None):
    """Return a SessionStore implementation chosen by *backend*.

    *backend* defaults to ``settings.session_store`` (env: ``SESSION_STORE``).
    Recognised values: ``"sqlite"`` (default), ``"memory"``.
    Unknown values fall back to SQLite with a warning.
    """
    chosen = (backend or settings.session_store or "sqlite").lower().strip()
    if chosen == "memory":
        return MemorySessionStore()
    if chosen == "sqlite":
        return SQLiteSessionStore()
    # Unknown backend — fall back gracefully.
    import warnings
    warnings.warn(
        f"Unknown SESSION_STORE value {chosen!r}; falling back to SQLite.",
        stacklevel=2,
    )
    return SQLiteSessionStore()
