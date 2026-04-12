"""features/transcription/service.py — TranscriptionService.

Wraps Groq Whisper (audio → text) and LLM transcript cleanup.
Extracted verbatim from main.py and providers.py.
"""

from __future__ import annotations

import httpx

from providers import ClientInputError, clean_transcript, resolve_api_key

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


class TranscriptionService:
    """Handles audio transcription and transcript cleanup."""

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._client = http_client

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        content_type: str,
        groq_api_key: str = "",
    ) -> str:
        """Transcribe audio using Groq Whisper large-v3-turbo.

        Returns the transcribed text string.
        Raises ClientInputError for invalid/missing key.
        Raises httpx.HTTPStatusError on API errors.
        """
        resolved_key = resolve_api_key("groq", groq_api_key)

        response = await self._client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {resolved_key}"},
            files={
                "file": (
                    filename or "audio.webm",
                    audio_bytes,
                    content_type or "audio/webm",
                )
            },
            data={
                "model": "whisper-large-v3-turbo",
                "response_format": "json",
                "language": "en",
            },
        )
        response.raise_for_status()
        return response.json().get("text", "").strip()

    async def clean(
        self,
        raw_transcript: str,
        provider: str = "groq",
        api_key: str = "",
        model: str = "",
    ) -> str:
        """Clean up a raw speech-to-text transcript via LLM.

        Returns the cleaned text, or the original if cleanup fails.
        Never raises — failures are non-fatal.
        """
        if not raw_transcript.strip():
            return ""
        return await clean_transcript(
            client=self._client,
            provider=provider,
            api_key=api_key,
            model=model,
            raw_transcript=raw_transcript,
        )
