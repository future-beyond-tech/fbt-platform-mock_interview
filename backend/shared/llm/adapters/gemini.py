"""shared/llm/adapters/gemini.py — Google Gemini / Gemma adapter."""

from __future__ import annotations

import httpx

from shared.llm.ports import LLMProvider

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiAdapter(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str = "") -> None:
        # api_key can also be supplied per-call via the `model` kwarg workaround;
        # the registry passes "" here and resolvers provide it at call time.
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
        model_name = model or "gemini-2.5-flash"
        is_gemma = model_name.startswith("gemma")

        # Gemma models reject systemInstruction — bake it into the first user turn.
        contents: list[dict] = []
        if is_gemma:
            stitched = (system + "\n\n" + messages[0]["content"]) if messages else system
            contents.append({"role": "user", "parts": [{"text": stitched}]})
            tail = messages[1:]
        else:
            tail = messages

        for m in tail:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        body: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if not is_gemma:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        r = await client.post(
            f"{_GEMINI_BASE}/{model_name}:generateContent",
            params={"key": key},
            json=body,
        )
        r.raise_for_status()
        data = r.json()

        if "error" in data:
            from providers import ProviderResponseError
            raise ProviderResponseError(
                f"Gemini API error: {data['error'].get('message', data['error'])}"
            )

        candidates = data.get("candidates", [])
        if not candidates:
            from providers import ProviderResponseError
            raise ProviderResponseError("Gemini returned no candidates")

        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts if p.get("text")).strip()

    async def is_available(self, client: httpx.AsyncClient) -> bool:
        return bool(self._default_key)
