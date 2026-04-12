"""shared/persistence/memory.py — In-process MemorySessionStore.

Suitable for development and testing.  Data is lost on process restart.
"""

from __future__ import annotations

import json


class MemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict] = {}

    def get(self, session_id: str) -> dict | None:
        data = self._sessions.get(session_id)
        return json.loads(json.dumps(data)) if data is not None else None

    def set(self, session_id: str, data: dict) -> None:
        self._sessions[session_id] = json.loads(json.dumps(data))

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
