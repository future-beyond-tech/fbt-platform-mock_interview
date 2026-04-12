"""
shared/llm/resilience.py — Retry + circuit-breaker logic for LLM calls.

Extracted verbatim from providers.py so it can be reused by both the legacy
providers module and the new feature service layer without duplication.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from typing import Any, Awaitable, Callable

import httpx

# ── Constants ─────────────────────────────────────────────────────────────────

# HTTP status codes that are transient and worth retrying.
# 503 = Google AI Studio "high demand"; 529 = Anthropic overload.
RETRY_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504, 529})

# How long (seconds) to mark a provider "sick" after it returns an overload status.
OVERLOAD_COOLDOWN_SECONDS: float = 60.0

# Per-provider cooldown deadline (event-loop time).
_provider_cooldown: dict[str, float] = {}


# ── Logging helper ─────────────────────────────────────────────────────────────

def _log(*args: Any, **kwargs: Any) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    print(f"[{ts}]", *args, **kwargs)


# ── Circuit breaker ────────────────────────────────────────────────────────────

def provider_is_sick(provider: str) -> bool:
    """Return True if *provider* is under overload cooldown."""
    deadline = _provider_cooldown.get(provider)
    if deadline is None:
        return False
    if asyncio.get_event_loop().time() >= deadline:
        _provider_cooldown.pop(provider, None)
        return False
    return True


def mark_provider_sick(provider: str) -> None:
    """Start a cooldown window for *provider*."""
    _provider_cooldown[provider] = (
        asyncio.get_event_loop().time() + OVERLOAD_COOLDOWN_SECONDS
    )
    _log(
        f"[circuit-breaker] {provider} marked sick for {OVERLOAD_COOLDOWN_SECONDS:.0f}s; "
        f"next calls will skip straight to fallback",
        file=sys.stderr,
    )


# ── Retry with exponential backoff ────────────────────────────────────────────

async def retry_with_backoff(
    fn: Callable[[], Awaitable[Any]],
    *,
    max_attempts: int = 2,
    base_delay: float = 0.3,
    max_delay: float = 2.0,
    label: str = "call",
    provider: str | None = None,
) -> Any:
    """Run *fn*, retrying on transient HTTP errors with exponential backoff.

    If *provider* is given and is currently under overload cooldown, raises a
    synthetic 503 immediately so the caller can fall back without paying the
    full retry cost.
    """
    if provider and provider_is_sick(provider):
        _log(
            f"[retry:{label}] skipping — {provider} is under overload cooldown",
            file=sys.stderr,
        )
        raise httpx.HTTPStatusError(
            f"{provider} under overload cooldown",
            request=httpx.Request("POST", "https://cooldown.local"),
            response=httpx.Response(503),
        )

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except httpx.HTTPStatusError as error:
            last_error = error
            status = error.response.status_code if error.response is not None else 0
            if status not in RETRY_STATUSES or attempt == max_attempts:
                if status in RETRY_STATUSES and provider:
                    mark_provider_sick(provider)
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            _log(
                f"[retry:{label}] attempt {attempt}/{max_attempts} failed with "
                f"HTTP {status}; sleeping {delay:.1f}s",
                file=sys.stderr,
            )
            await asyncio.sleep(delay)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as error:
            last_error = error
            if attempt == max_attempts:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            _log(
                f"[retry:{label}] attempt {attempt}/{max_attempts} network error: "
                f"{error}; sleeping {delay:.1f}s",
                file=sys.stderr,
            )
            await asyncio.sleep(delay)

    if last_error:
        raise last_error
    raise RuntimeError("retry_with_backoff exhausted with no error captured")


# ── Backward-compatible aliases (providers.py used private names) ─────────────
# These let us keep `from shared.llm.resilience import _retry_with_backoff` style
# imports in providers.py without changing every call site.
_retry_with_backoff = retry_with_backoff
_provider_sick = provider_is_sick
_mark_provider_sick = mark_provider_sick
