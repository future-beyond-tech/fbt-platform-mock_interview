"""features/transcription/router.py — FastAPI router for transcription endpoints.

Moves POST /api/transcribe and POST /api/clean-transcript out of main.py.
Zero API contract changes.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from providers import ClientInputError
from features.transcription.service import TranscriptionService, MAX_UPLOAD_BYTES

router = APIRouter(prefix="/api", tags=["transcription"])


def _http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client


def _http_error_detail(error: httpx.HTTPStatusError) -> str:
    body = error.response.text[:200] if error.response is not None else str(error)
    return body or str(error)


class CleanTranscriptRequest(BaseModel):
    raw_transcript: str
    provider: str = "groq"
    api_key: str = ""
    model: str = ""


@router.post("/transcribe")
async def transcribe(
    request: Request,
    audio: UploadFile = File(...),
    groq_api_key: str = Form(""),
):
    """Transcribe audio using Groq Whisper large-v3-turbo."""
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")
    if len(audio_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large — max 10 MB.")

    service = TranscriptionService(_http_client(request))
    try:
        text = await service.transcribe(
            audio_bytes,
            filename=audio.filename or "audio.webm",
            content_type=audio.content_type or "audio/webm",
            groq_api_key=groq_api_key,
        )
    except ClientInputError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except httpx.HTTPStatusError as error:
        raise HTTPException(status_code=502, detail=f"Groq Whisper error: {_http_error_detail(error)}")
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {error}")

    return {"text": text}


@router.post("/clean-transcript")
async def clean_transcript_endpoint(req: CleanTranscriptRequest, request: Request):
    """Clean up a raw speech-to-text transcript via LLM."""
    if not req.raw_transcript.strip():
        return {"text": ""}

    service = TranscriptionService(_http_client(request))
    cleaned = await service.clean(
        req.raw_transcript,
        provider=req.provider,
        api_key=req.api_key,
        model=req.model,
    )
    return {"text": cleaned}
