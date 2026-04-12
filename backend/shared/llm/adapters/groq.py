"""shared/llm/adapters/groq.py — Groq (OpenAI-compatible) adapter."""

from __future__ import annotations

import httpx

from shared.llm.ports import LLMProvider

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "llama-3.1-8b-instant"


class GroqAdapter(LLMProvider):
    name = "groq"

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
        chat_messages = ([{"role": "system", "content": system}] if system else []) + messages
        r = await client.post(
            _GROQ_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model or _DEFAULT_MODEL,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": chat_messages,
            },
        )
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip()

    async def is_available(self, client: httpx.AsyncClient) -> bool:
        return bool(self._default_key)
