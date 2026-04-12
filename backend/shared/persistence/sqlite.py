"""shared/persistence/sqlite.py — SQLite-backed SessionStore.

Uses WAL mode for safe concurrent reads.  Sessions survive process restarts.
db_path defaults to backend/.runtime/interview_sessions.sqlite3 and can be
overridden via the INTERVIEW_SESSION_DB_PATH env variable or the constructor.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from config import get_config_value


class SQLiteSessionStore:
    def __init__(self, db_path: str | os.PathLike[str] | None = None) -> None:
        default_path = Path(__file__).resolve().parent.parent.parent / ".runtime" / "interview_sessions.sqlite3"
        configured_path = db_path or get_config_value("INTERVIEW_SESSION_DB_PATH", "")
        self.db_path = Path(configured_path or default_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS interview_sessions (
                    session_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def get(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM interview_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"])

    def set(self, session_id: str, data: dict) -> None:
        payload = json.dumps(data)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO interview_sessions (session_id, payload, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (session_id, payload),
            )
            conn.commit()

    def delete(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM interview_sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
