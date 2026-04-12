"""shared/llm/adapters/ollama.py — Ollama (local) LLM adapter."""

from __future__ import annotations

import httpx

from config import settings
from shared.llm.ports import LLMProvider


class OllamaAdapter(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")

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
        # Ollama's /api/generate does not natively support a message list,
        # so we stitch system + history into a single prompt string.
        history = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in messages
        )
        full_prompt = f"{system}\n\n{history}\nASSISTANT:" if system else f"{history}\nASSISTANT:"

        r = await client.post(
            f"{self._base_url}/api/generate",
            json={
                "model": model or "llama3:latest",
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
        )
        r.raise_for_status()
        return (r.json().get("response") or "").strip()

    async def is_available(self, client: httpx.AsyncClient) -> bool:
        try:
            r = await client.get(f"{self._base_url}/api/tags", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False
