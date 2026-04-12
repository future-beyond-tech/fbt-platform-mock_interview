"""
shared/llm/ports.py — Abstract LLM provider contract.

Every concrete adapter must implement this interface.  The `chat()` method
is the single entry point: it accepts a system prompt and a list of
{"role": "user"|"assistant", "content": str} messages and returns plain text.

Callers that need JSON should parse the returned string themselves — we do
NOT bake JSON-mode into the contract because not every provider supports it
natively and keeping parsing in the service layer gives us full control.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import httpx


class LLMProvider(ABC):
    """Abstract base for every LLM provider adapter."""

    #: Short identifier — matches the key used in the registry (e.g. "ollama").
    name: str

    @abstractmethod
    async def chat(
        self,
        client: httpx.AsyncClient,
        system: str,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> str:
        """Single-turn or multi-turn chat completion.

        Args:
            client:      Shared ``httpx.AsyncClient`` from the FastAPI lifespan.
            system:      System / instruction prompt (empty string = no system).
            messages:    Conversation history — list of
                         ``{"role": "user"|"assistant", "content": str}``.
            model:       Model name/tag to use.  Empty string → adapter default.
            temperature: Sampling temperature (0.0 – 1.0).
            max_tokens:  Maximum tokens to generate.

        Returns:
            The model's reply as a plain string (no markup stripping applied).

        Raises:
            httpx.HTTPStatusError:  On non-2xx responses.
            httpx.ConnectError:     When the provider is unreachable.
        """

    @abstractmethod
    async def is_available(self, client: httpx.AsyncClient) -> bool:
        """Return True if this provider is reachable right now."""
