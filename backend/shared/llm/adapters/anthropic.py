"""shared/llm/adapters/anthropic.py — Anthropic (Claude) adapter."""

from __future__ import annotations

import httpx

from shared.llm.ports import LLMProvider

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-sonnet-4-20250514"


class AnthropicAdapter(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str = "") -> None:
        self._default_key = api_key

    async def chat(
        self,
        client: httpx.AsyncClient,
        system: str,
        messages: list[dict],
        *,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        api_key: str = "",
    ) -> str:
        key = api_key or self._default_key
        body: dict = {
            "model": model or _DEFAULT_MODEL,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            body["system"] = system

        r = await client.post(
            _ANTHROPIC_URL,
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json=body,
        )
        r.raise_for_status()
        data = r.json()
        return "".join(
            c["text"] for c in data["content"] if c["type"] == "text"
        ).strip()

    async def is_available(self, client: httpx.AsyncClient) -> bool:
        return bool(self._default_key)
