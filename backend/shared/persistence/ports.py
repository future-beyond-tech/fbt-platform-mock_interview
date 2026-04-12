"""shared/persistence/ports.py — Abstract SessionStore protocol.

Any concrete store must implement get/set/delete so that feature routers
and the interview slice can treat all stores identically.
"""

from __future__ import annotations

from typing import Protocol


class SessionStore(Protocol):
    def get(self, session_id: str) -> dict | None: ...
    def set(self, session_id: str, data: dict) -> None: ...
    def delete(self, session_id: str) -> None: ...
