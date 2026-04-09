"""
Multi-provider LLM abstraction.
Supports: Ollama (local), Groq, Google Gemini, OpenAI, Anthropic.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from typing import Any, Awaitable, Callable

import httpx

# ─── Retry + provider fallback ────────────────────────────
# Transient HTTP statuses worth retrying. 503 is the Google AI Studio
# "high demand" overload code; 529 is Anthropic's overload; 500/502/504 are
# generic transient gateway errors.
RETRY_STATUSES: set[int] = {500, 502, 503, 504, 529}


async def _retry_with_backoff(
    fn: Callable[[], Awaitable[Any]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
    label: str = "call",
) -> Any:
    """Run `fn`, retrying on transient HTTP errors with exponential backoff."""
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except httpx.HTTPStatusError as error:
            last_error = error
            status = error.response.status_code if error.response is not None else 0
            if status not in RETRY_STATUSES or attempt == max_attempts:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            print(
                f"[retry:{label}] attempt {attempt}/{max_attempts} failed with HTTP {status}; "
                f"sleeping {delay:.1f}s",
                file=sys.stderr,
            )
            await asyncio.sleep(delay)
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as error:
            last_error = error
            if attempt == max_attempts:
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            print(
                f"[retry:{label}] attempt {attempt}/{max_attempts} network error: {error}; "
                f"sleeping {delay:.1f}s",
                file=sys.stderr,
            )
            await asyncio.sleep(delay)
    if last_error:
        raise last_error
    raise RuntimeError("retry_with_backoff exhausted with no error captured")

ENV_KEY_NAMES = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
PROVIDER_DISPLAY_NAMES = {
    "gemini": "Google Gemini",
    "groq": "Groq",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
}


class ClientInputError(ValueError):
    """Invalid user input or missing configuration."""


class ProviderResponseError(RuntimeError):
    """Provider returned a response we could not use safely."""


def resolve_api_key(provider: str, api_key: str) -> str:
    if provider == "ollama":
        return ""

    if provider not in PROVIDER_DISPLAY_NAMES:
        raise ClientInputError(f"Unknown provider: {provider}")

    if api_key and api_key.strip():
        return api_key.strip()

    env_name = ENV_KEY_NAMES[provider]
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return env_value

    raise ClientInputError(f"{PROVIDER_DISPLAY_NAMES[provider]} API key is required")

EVAL_SYSTEM = (
    "You are a senior JavaScript/React technical interviewer evaluating a candidate with 8+ years of experience. "
    "You evaluate answers SEMANTICALLY — you understand the INTENT and KNOWLEDGE behind words, "
    "not just literal phrasing. The candidate may have used voice-to-text, so minor transcription "
    "errors (e.g. 'letten' for 'let and', 'ESG' for 'ES6', 'temporal dead son' for 'temporal dead zone') "
    "should be interpreted charitably as the correct technical term. "
    "Judge what the candidate KNOWS, not how perfectly they phrased it."
)

def build_eval_prompt(section: str, question: str, answer: str) -> str:
    return f"""Section: {section}
Question: {question}
Candidate answer: {answer}

EVALUATION INSTRUCTIONS:
1. SEMANTIC INTERPRETATION: First, mentally correct any obvious voice transcription errors in the answer (e.g. "letten const" → "let and const", "ESG6" → "ES6", "temporal dead son" → "temporal dead zone"). Evaluate the corrected meaning.

2. CONCEPT EXTRACTION: Identify the 3-5 key concepts this question requires. For each concept, determine if the candidate demonstrated understanding (even partially or indirectly).

3. SCORING RUBRIC:
   - 85-100 (correct): Covers all key concepts accurately, even if not perfectly worded
   - 50-84 (partial): Demonstrates clear understanding of some concepts but misses others
   - 20-49 (partial): Shows awareness of the topic but with significant gaps
   - 0-19 (incorrect): Does not demonstrate meaningful understanding of the core concepts

4. VERDICT RULES:
   - "correct" if score >= 75
   - "partial" if score >= 30
   - "incorrect" if score < 30

Respond with ONLY a raw JSON object — no markdown, no backticks, no explanation outside the JSON:
{{"score": <integer 0-100>, "verdict": "correct"|"partial"|"incorrect", "strength": "<specific concepts they demonstrated correctly — be generous with partial credit>", "missing": "<specific concepts not covered or incorrect — be precise>", "hint": "<Socratic question pointing toward the gap, empty string if correct>", "ideal": "<concise ideal answer covering all key concepts in 2-3 sentences>"}}"""


def parse_eval_json(text: str) -> dict | None:
    """Extract evaluation JSON from any LLM output."""
    import sys
    if not text or not text.strip():
        print(f"[parse_eval_json] Empty text received", file=sys.stderr)
        return None

    # Remove markdown fences and leading/trailing whitespace
    cleaned = re.sub(r"```(?:json)?```?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()

    # Find outermost JSON object
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        print(f"[parse_eval_json] No JSON object found. Raw text (200 chars): {repr(text[:200])}", file=sys.stderr)
        return None

    json_str = cleaned[start : end + 1]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"[parse_eval_json] JSON parse error: {e}. Snippet: {repr(json_str[:200])}", file=sys.stderr)
        return None

    if "score" not in data or "verdict" not in data:
        print(f"[parse_eval_json] Missing required fields. Got keys: {list(data.keys())}", file=sys.stderr)
        return None

    score = max(0, min(100, int(data.get("score", 0))))
    verdict = data.get("verdict", "incorrect")
    if verdict not in ("correct", "partial", "incorrect"):
        verdict = "incorrect"
    return {
        "score": score,
        "verdict": verdict,
        "strength": str(data.get("strength", ""))[:500],
        "missing": str(data.get("missing", ""))[:500],
        "hint": str(data.get("hint", ""))[:500],
        "ideal": str(data.get("ideal", ""))[:1000],
    }


# ─── Ollama ───────────────────────────────────────────────
async def call_ollama(
    client: httpx.AsyncClient,
    model: str,
    section: str,
    question: str,
    answer: str,
    profile: dict | None = None,
    base_url: str = "http://localhost:11434",
) -> dict:
    prompt = build_role_aware_eval_prompt(section, question, answer, profile)
    r = await client.post(
        f"{base_url}/api/generate",
        json={
            "model": model or "llama3:latest",
            "prompt": f"{EVAL_SYSTEM}\n\n{prompt}",
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 512},
        },
    )
    r.raise_for_status()
    return parse_eval_json(r.json().get("response", ""))


# ─── Google Gemini ────────────────────────────────────────
async def call_gemini(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    section: str,
    question: str,
    answer: str,
    profile: dict | None = None,
) -> dict:
    prompt = build_role_aware_eval_prompt(section, question, answer, profile)
    model_name = model or "gemini-2.5-flash"
    is_gemma = model_name.startswith("gemma")
    generation_config: dict = {"temperature": 0.3, "maxOutputTokens": 2048}
    if not is_gemma:
        # Gemma models on the Gemini API do not support responseMimeType.
        generation_config["responseMimeType"] = "application/json"
    r = await client.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": f"{EVAL_SYSTEM}\n\n{prompt}"}]}],
            "generationConfig": generation_config,
        },
    )
    r.raise_for_status()
    data = r.json()

    import sys
    if "error" in data:
        raise ProviderResponseError(f"Gemini API error: {data['error'].get('message', data['error'])}")

    candidates = data.get("candidates", [])
    if not candidates:
        print(f"[Gemini] No candidates in response: {data}", file=sys.stderr)
        raise ProviderResponseError("Gemini returned no candidates")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if p.get("text"))
    print(f"[Gemini] Raw text (200): {repr(text[:200])}", file=sys.stderr)
    return parse_eval_json(text)


# ─── OpenAI ───────────────────────────────────────────────
async def call_openai(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    section: str,
    question: str,
    answer: str,
    profile: dict | None = None,
) -> dict:
    prompt = build_role_aware_eval_prompt(section, question, answer, profile)
    r = await client.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model or "gpt-4o-mini",
            "temperature": 0.3,
            "max_tokens": 512,
            "messages": [
                {"role": "system", "content": EVAL_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        },
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    return parse_eval_json(text)


# ─── Groq ────────────────────────────────────────────────
async def call_groq(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    section: str,
    question: str,
    answer: str,
    profile: dict | None = None,
) -> dict:
    prompt = build_role_aware_eval_prompt(section, question, answer, profile)
    r = await client.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model or "llama-3.3-70b-versatile",
            "temperature": 0.3,
            "max_tokens": 512,
            "messages": [
                {"role": "system", "content": EVAL_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        },
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"]
    return parse_eval_json(text)


# ─── Anthropic ────────────────────────────────────────────
async def call_anthropic(
    client: httpx.AsyncClient,
    api_key: str,
    model: str,
    section: str,
    question: str,
    answer: str,
    profile: dict | None = None,
) -> dict:
    prompt = build_role_aware_eval_prompt(section, question, answer, profile)
    r = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json={
            "model": model or "claude-sonnet-4-20250514",
            "max_tokens": 512,
            "system": EVAL_SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    r.raise_for_status()
    data = r.json()
    text = "".join(c["text"] for c in data["content"] if c["type"] == "text")
    return parse_eval_json(text)


# ─── Router ──────────────────────────────────────────────
PROVIDERS = {
    "ollama": call_ollama,
    "gemini": call_gemini,
    "groq": call_groq,
    "openai": call_openai,
    "anthropic": call_anthropic,
}

async def _evaluate_once(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    section: str,
    question: str,
    answer: str,
    profile: dict | None,
) -> dict:
    """Single evaluation attempt for one provider — used by retry+fallback wrapper."""
    if provider == "ollama":
        return await call_ollama(client, model, section, question, answer, profile=profile)

    resolved_key = resolve_api_key(provider, api_key)
    if provider == "gemini":
        return await call_gemini(client, resolved_key, model, section, question, answer, profile=profile)
    if provider == "groq":
        return await call_groq(client, resolved_key, model, section, question, answer, profile=profile)
    if provider == "openai":
        return await call_openai(client, resolved_key, model, section, question, answer, profile=profile)
    if provider == "anthropic":
        return await call_anthropic(client, resolved_key, model, section, question, answer, profile=profile)
    raise ClientInputError(f"Unknown provider: {provider}")


async def evaluate_with_provider(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    section: str,
    question: str,
    answer: str,
    profile: dict | None = None,
) -> dict:
    """Route to the correct provider with retry+backoff. Falls back to Groq on exhaustion."""

    async def _primary() -> dict:
        return await _evaluate_once(client, provider, api_key, model, section, question, answer, profile)

    try:
        return await _retry_with_backoff(_primary, max_attempts=3, label=f"eval:{provider}")
    except (httpx.HTTPStatusError, httpx.RequestError) as primary_error:
        if provider == "groq" or provider == "ollama":
            raise

        # Try Groq fallback if a key is available.
        try:
            resolve_api_key("groq", "")
        except ClientInputError:
            print(
                f"[fallback:eval] {provider} exhausted retries and no GROQ_API_KEY is set; "
                f"surfacing original error",
                file=sys.stderr,
            )
            raise primary_error

        print(
            f"[fallback:eval] {provider} exhausted retries; falling back to Groq "
            f"({GROQ_FALLBACK_MODEL})",
            file=sys.stderr,
        )

        async def _fallback() -> dict:
            return await _evaluate_once(
                client, "groq", "", GROQ_FALLBACK_MODEL,
                section, question, answer, profile,
            )

        return await _retry_with_backoff(_fallback, max_attempts=2, label="eval:groq")


# ─── Question generation ──────────────────────────────────

def build_question_gen_prompt(topic: str, count: int) -> str:
    focus = f"Focus specifically on: {topic}." if topic else \
        "Cover a mix of: JS Core concepts, async/promises, React hooks, performance, and system design."
    return f"""You are a senior JavaScript/React technical interviewer with 15 years experience.

Generate exactly {count} technical interview questions for a candidate with 8+ years of experience.

{focus}

STRICT RULES:
- Return ONLY a valid JSON array — no markdown, no backticks, no explanation.
- Each item must have exactly these fields: {{"id": string, "q": string, "s": string, "day": 0}}
  - "id": unique short id like "gen01", "gen02", etc.
  - "q": the full interview question (be specific, scenario-based, not generic)
  - "s": category label e.g. "React Hooks", "JS Core", "Performance", "System Design"
  - "day": always 0 (indicates AI-generated)
- Mix difficulty: at least one deep conceptual, one practical/code, one scenario-based.
- Questions must require explanation, not yes/no answers.

Return ONLY the JSON array, nothing else."""


async def _call_llm_for_questions(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    prompt: str,
) -> list:
    """Call the appropriate LLM and return parsed question list."""
    import sys

    text = ""
    if provider == "ollama":
        r = await client.post(
            "http://localhost:11434/api/generate",
            json={"model": model or "llama3:latest", "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.7, "num_predict": 1024}},
        )
        r.raise_for_status()
        text = r.json().get("response", "")

    elif provider == "gemini":
        model_name = model or "gemini-2.5-flash"
        is_gemma = model_name.startswith("gemma")
        gen_config: dict = {"temperature": 0.7, "maxOutputTokens": 2048}
        if not is_gemma:
            gen_config["responseMimeType"] = "application/json"
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
            params={"key": api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": gen_config,
            },
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise ProviderResponseError(f"Gemini API error: {data['error'].get('message', data['error'])}")
        candidates = data.get("candidates", [])
        if not candidates:
            raise ProviderResponseError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts if p.get("text"))

    elif provider in ("groq", "openai", "anthropic"):
        if provider == "groq":
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}"}
            mdl = model or "llama-3.3-70b-versatile"
        elif provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}"}
            mdl = model or "gpt-4o-mini"
        else:  # anthropic — use openai-compat via messages
            r2 = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                         "Content-Type": "application/json"},
                json={"model": model or "claude-sonnet-4-20250514", "max_tokens": 1024,
                      "messages": [{"role": "user", "content": prompt}]},
            )
            r2.raise_for_status()
            data2 = r2.json()
            text = "".join(c["text"] for c in data2["content"] if c["type"] == "text")
            mdl = None

        if provider in ("groq", "openai"):
            r = await client.post(url, headers=headers,
                json={"model": mdl, "temperature": 0.7, "max_tokens": 2048,
                      "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]
    else:
        raise ClientInputError(f"Unknown provider: {provider}")

    print(f"[gen] raw (len={len(text)}): {repr(text[:400])}", file=sys.stderr)

    # Parse JSON — accept either an array of questions or a single question object
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()

    arr_start = cleaned.find("[")
    arr_end = cleaned.rfind("]")
    obj_start = cleaned.find("{")
    obj_end = cleaned.rfind("}")

    questions = None
    # Prefer array if it appears before any object (or no object at all)
    if arr_start != -1 and arr_end > arr_start and (obj_start == -1 or arr_start < obj_start):
        try:
            questions = json.loads(cleaned[arr_start:arr_end + 1])
        except json.JSONDecodeError:
            questions = None

    if questions is None and obj_start != -1 and obj_end > obj_start:
        try:
            single = json.loads(cleaned[obj_start:obj_end + 1])
            questions = [single] if isinstance(single, dict) else None
        except json.JSONDecodeError as error:
            raise ProviderResponseError(f"Could not parse generated questions: {error.msg}") from error

    if questions is None:
        raise ProviderResponseError(f"No JSON in response: {repr(text[:150])}")

    if not isinstance(questions, list):
        raise ProviderResponseError("Provider did not return a question list")

    # Validate and normalise each question
    result = []
    for i, q in enumerate(questions):
        if not isinstance(q, dict) or "q" not in q:
            continue
        result.append({
            "id": q.get("id") or f"gen{i+1:02d}",
            "q": str(q["q"]).strip(),
            "s": str(q.get("s") or q.get("category") or "AI Generated").strip(),
            "day": 0,
        })
    return result


def _extract_pdf_text(file_bytes: bytes) -> str:
    """Extract plain text from a PDF file."""
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(file_bytes))
    parts = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            parts.append(t.strip())
    return "\n\n".join(parts)[:6000]  # cap to avoid token blowout


def _image_to_base64(file_bytes: bytes, content_type: str) -> str:
    import base64
    return base64.b64encode(file_bytes).decode()


def _build_file_question_prompt(text_content: str) -> str:
    return f"""You are a senior JavaScript/React technical interviewer.

The candidate has uploaded the following content (CV, resume, screenshot, or document):

---
{text_content}
---

Based ONLY on the content above, generate exactly ONE challenging technical interview question that:
- Is directly relevant to the technologies, projects, or skills mentioned
- Requires the candidate to explain, justify, or demonstrate understanding
- Is specific (not generic) — reference something actually in the content
- Is suitable for a senior engineer (8+ years experience)

STRICT RULES:
- Return ONLY a valid JSON array containing exactly ONE question object — no markdown, no backticks, no explanation outside JSON.
- Format: [{{"id": "file01", "q": "<the full question>", "s": "<short category e.g. React, System Design, JS Core>", "day": 0}}]

Return ONLY the JSON array."""


async def generate_question_from_file(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    file_bytes: bytes,
    content_type: str,
    filename: str,
) -> dict:
    """Extract content from PDF or image, generate 1 interview question."""
    import sys

    resolved_key = resolve_api_key(provider, api_key)

    is_pdf = "pdf" in content_type or filename.lower().endswith(".pdf")
    is_image = content_type.startswith("image/") or filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))

    if is_pdf:
        text_content = _extract_pdf_text(file_bytes)
        if not text_content.strip():
            raise ClientInputError("Could not extract text from PDF")
        prompt = _build_file_question_prompt(text_content)
        # Text-only path for all providers
        result = await _call_llm_for_questions(client, provider, resolved_key, model, prompt)
    elif is_image:
        # Vision path: use provider's vision capability
        img_b64 = _image_to_base64(file_bytes, content_type)
        mime = content_type if content_type.startswith("image/") else "image/jpeg"

        vision_prompt = (
            "You are a senior JavaScript/React technical interviewer. "
            "Look at this image (it could be a CV, code, architecture diagram, or resume). "
            "Based ONLY on what you see, generate exactly ONE challenging technical interview question "
            "that is directly relevant to the content. The question should be specific and suitable for "
            "a senior engineer (8+ years experience). "
            "Return ONLY a raw JSON object — no markdown, no backticks: "
            '{"id": "file01", "q": "<full question>", "s": "<category>", "day": 0}'
        )

        text = ""
        if provider == "gemini":
            model_name = model or "gemini-2.5-flash"
            if model_name.startswith("gemma"):
                raise ClientInputError(
                    "Gemma models do not support image input. "
                    "Pick a Gemini model (e.g. gemini-2.5-flash) for image uploads, or upload a PDF instead."
                )
            r = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
                params={"key": resolved_key},
                json={
                    "contents": [{"parts": [
                        {"text": vision_prompt},
                        {"inline_data": {"mime_type": mime, "data": img_b64}},
                    ]}],
                    "generationConfig": {"temperature": 0.7, "maxOutputTokens": 512},
                },
            )
            r.raise_for_status()
            data = r.json()
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if p.get("text"))

        elif provider == "openai":
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {resolved_key}"},
                json={
                    "model": model or "gpt-4o-mini",
                    "max_tokens": 512,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": vision_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                    ]}],
                },
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"]

        elif provider == "anthropic":
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": resolved_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={
                    "model": model or "claude-sonnet-4-20250514",
                    "max_tokens": 512,
                    "messages": [{"role": "user", "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": mime, "data": img_b64}},
                        {"type": "text", "text": vision_prompt},
                    ]}],
                },
            )
            r.raise_for_status()
            data = r.json()
            text = "".join(c["text"] for c in data["content"] if c["type"] == "text")

        else:
            # Groq / Ollama don't support vision natively — extract via OCR hint fallback
            raise ClientInputError(f"Provider '{provider}' does not support image vision. Use Gemini, OpenAI, or Anthropic for images, or upload a PDF.")

        print(f"[file-vision] raw (200): {repr(text[:200])}", file=sys.stderr)
        # Parse single JSON object
        cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"```", "", cleaned).strip()
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            raise ProviderResponseError(f"No JSON object in vision response: {repr(text[:150])}")
        try:
            q = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as error:
            raise ProviderResponseError(f"Could not parse file question: {error.msg}") from error
        result = [{"id": q.get("id", "file01"), "q": str(q["q"]).strip(), "s": str(q.get("s", "AI Generated")).strip(), "day": 0}]
    else:
        raise ClientInputError("Unsupported file type. Please upload a PDF or image (PNG, JPG, WEBP, GIF).")

    if not result:
        raise ProviderResponseError("Could not generate a question from this file")
    return result[0]


async def generate_questions_with_provider(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    topic: str,
    count: int,
) -> list:
    """Generate interview questions using the selected provider."""
    prompt = build_question_gen_prompt(topic, count)
    resolved_key = resolve_api_key(provider, api_key)
    return await _call_llm_for_questions(client, provider, resolved_key, model, prompt)


# ─── Interview conversation (multi-turn) ──────────────────

def build_interviewer_system_prompt(profile: dict | None) -> str:
    if profile:
        domain = profile.get("domain") or "General"
        role = (profile.get("roles") or ["Professional"])[0]
        level = profile.get("experienceLevel") or "mid"
        years = profile.get("yearsOfExperience") or 0
        is_tech = bool(profile.get("isTechnical", True))
        persona = (
            f"a senior {domain} professional and hiring manager interviewing a {level} {role} "
            f"with {years} years of experience"
        )
        domain_rule = (
            ""
            if is_tech
            else (
                f"\nDOMAIN RULES:\n"
                f"- This candidate is in {domain}, NOT software engineering.\n"
                f"- DO NOT ask about programming, code, frameworks, or technical CS topics.\n"
                f"- Ask {domain}-specific questions appropriate to a {role}.\n"
            )
        )
    else:
        persona = "a senior interviewer conducting a real job interview"
        domain_rule = ""

    return f"""You are {persona}.
Follow this conversation flow:

PHASE 1 - INTRODUCTION (1 exchange):
- Greet the candidate warmly, ask them to walk through their background.

PHASE 2 - PROJECT / EXPERIENCE DEEP DIVE (2-3 exchanges):
- Ask about specific projects, classes, campaigns, cases, or experiences they mentioned.
- Focus on what they did, their role, the context, and challenges faced.

PHASE 3 - SKILL-BASED QUESTIONS (5-8 exchanges):
- Pick concrete skills or competencies from their resume / answers.
- Start basic and adapt difficulty based on answer quality.
- Always connect questions to their real experience and domain.

PHASE 4 - ADVANCED / SITUATIONAL (2-3 exchanges):
- Scenario, judgement, or strategic questions appropriate to their level.

PHASE 5 - WRAP UP:
- Invite their questions, then close warmly.
{domain_rule}
RULES:
- Ask ONE question at a time. Never multiple questions together.
- Reference something they said previously when possible.
- Sound natural — use phrases like "Got it.", "Interesting!", "That makes sense."
- Never repeat a question already asked.
- Match the candidate's domain and experience level — do NOT default to software engineering topics unless they ARE a software engineer.
- Output ONLY the next interviewer message — no JSON, no markdown, no commentary, no labels.
"""


def build_interview_user_prompt(state: dict, resume_text: str, profile: dict | None = None) -> str:
    skills = ", ".join(state.get("extractedSkills", [])) or "none yet"
    projects = ", ".join(state.get("extractedProjects", [])) or "none yet"
    asked = "\n".join(f"- {q}" for q in state.get("questionsAsked", [])) or "(none)"
    profile_block = ""
    if profile:
        profile_block = (
            f"\nCANDIDATE PROFILE:\n"
            f"- Domain: {profile.get('domain')}\n"
            f"- Role: {(profile.get('roles') or ['Professional'])[0]}\n"
            f"- Experience: {profile.get('experienceLevel')} ({profile.get('yearsOfExperience', 0)} yrs)\n"
            f"- Is technical: {profile.get('isTechnical', True)}\n"
            f"- Top skills from resume: {', '.join(profile.get('topSkills') or []) or 'none listed'}\n"
        )
    return f"""CANDIDATE RESUME / DOCUMENT:
---
{resume_text[:4000]}
---
{profile_block}
INTERVIEW STATE:
- Current phase: {state.get('phase', 'introduction')}
- Question count so far: {state.get('questionCount', 0)}
- Difficulty level (1=basic, 2=intermediate, 3=advanced): {state.get('difficultyLevel', 1)}
- Last answer quality: {state.get('lastAnswerQuality', 'n/a')}
- Skills extracted from answers so far: {skills}
- Projects extracted: {projects}

QUESTIONS ALREADY ASKED:
{asked}

Generate the NEXT interviewer message based on the conversation history. Stay in phase {state.get('phase', 'introduction')}, adapt to difficulty {state.get('difficultyLevel', 1)}, and reference the candidate's previous answers naturally. Make sure the question is appropriate to their domain and role."""


async def _call_chat_text(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 1024,
) -> str:
    """Generic single-turn chat completion that returns plain text.

    `messages` is a list of {"role": "user"|"assistant", "content": str} entries.
    """
    if provider == "ollama":
        # Stitch a single prompt for Ollama's /api/generate
        history = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        full = f"{system}\n\n{history}\nASSISTANT:"
        r = await client.post(
            "http://localhost:11434/api/generate",
            json={"model": model or "llama3:latest", "prompt": full, "stream": False,
                  "options": {"temperature": temperature, "num_predict": max_tokens}},
        )
        r.raise_for_status()
        return (r.json().get("response") or "").strip()

    if provider == "gemini":
        model_name = model or "gemini-2.5-flash"
        is_gemma = model_name.startswith("gemma")
        # Gemma rejects systemInstruction; bake it into the first user message instead.
        contents = []
        if is_gemma:
            stitched = system + "\n\n" + (messages[0]["content"] if messages else "")
            contents.append({"role": "user", "parts": [{"text": stitched}]})
            tail = messages[1:]
        else:
            tail = messages
        for m in tail:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        body: dict = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if not is_gemma:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent",
            params={"key": api_key},
            json=body,
        )
        r.raise_for_status()
        data = r.json()
        if "error" in data:
            raise ProviderResponseError(f"Gemini API error: {data['error'].get('message', data['error'])}")
        candidates = data.get("candidates", [])
        if not candidates:
            raise ProviderResponseError("Gemini returned no candidates")
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts if p.get("text")).strip()

    if provider in ("groq", "openai"):
        url = ("https://api.groq.com/openai/v1/chat/completions" if provider == "groq"
               else "https://api.openai.com/v1/chat/completions")
        mdl = model or ("llama-3.3-70b-versatile" if provider == "groq" else "gpt-4o-mini")
        chat_messages = [{"role": "system", "content": system}] + messages
        r = await client.post(url, headers={"Authorization": f"Bearer {api_key}"},
            json={"model": mdl, "temperature": temperature, "max_tokens": max_tokens,
                  "messages": chat_messages})
        r.raise_for_status()
        return (r.json()["choices"][0]["message"]["content"] or "").strip()

    if provider == "anthropic":
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
            json={"model": model or "claude-sonnet-4-20250514", "max_tokens": max_tokens,
                  "system": system, "messages": messages},
        )
        r.raise_for_status()
        data = r.json()
        return "".join(c["text"] for c in data["content"] if c["type"] == "text").strip()

    raise ClientInputError(f"Unknown provider: {provider}")


# ─── Chat-text fallback chain ─────────────────────────────
# Default Groq chat model used when the primary provider exhausts retries.
GROQ_FALLBACK_MODEL = "llama-3.3-70b-versatile"


async def _call_chat_text_with_fallback(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict],
    *,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    label: str = "chat",
) -> str:
    """Call _call_chat_text with retry+backoff. On exhaustion, fall back to Groq.

    The fallback uses GROQ_API_KEY from the environment (loaded from .env).
    If the primary provider IS already Groq, we just retry without falling back.
    """

    async def _primary() -> str:
        return await _call_chat_text(
            client, provider, api_key, model, system, messages,
            temperature=temperature, max_tokens=max_tokens,
        )

    try:
        return await _retry_with_backoff(_primary, max_attempts=3, label=f"{label}:{provider}")
    except (httpx.HTTPStatusError, httpx.RequestError) as primary_error:
        if provider == "groq":
            raise  # already on the fallback target

        # Try the Groq fallback if a key is available.
        try:
            groq_key = resolve_api_key("groq", "")
        except ClientInputError:
            print(
                f"[fallback:{label}] {provider} exhausted retries and no GROQ_API_KEY is set; "
                f"surfacing original error",
                file=sys.stderr,
            )
            raise primary_error

        print(
            f"[fallback:{label}] {provider} exhausted retries; falling back to Groq "
            f"({GROQ_FALLBACK_MODEL})",
            file=sys.stderr,
        )

        async def _fallback() -> str:
            return await _call_chat_text(
                client, "groq", groq_key, GROQ_FALLBACK_MODEL, system, messages,
                temperature=temperature, max_tokens=max_tokens,
            )

        try:
            return await _retry_with_backoff(_fallback, max_attempts=2, label=f"{label}:groq")
        except Exception as fallback_error:
            print(
                f"[fallback:{label}] groq fallback also failed: {fallback_error}",
                file=sys.stderr,
            )
            raise


async def interview_next_question(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    state: dict,
    resume_text: str,
    history: list[dict],
    profile: dict | None = None,
) -> str:
    """Generate the next interviewer message given the conversation history."""
    resolved_key = resolve_api_key(provider, api_key)
    user_prompt = build_interview_user_prompt(state, resume_text, profile=profile)
    system_prompt = build_interviewer_system_prompt(profile)
    # Append the user_prompt as the latest user turn so the model has fresh state context.
    messages = history + [{"role": "user", "content": user_prompt}]
    text = await _call_chat_text_with_fallback(
        client, provider, resolved_key, model,
        system=system_prompt,
        messages=messages,
        temperature=0.7,
        max_tokens=512,
        label="interview",
    )
    # Some models prefix with "Interviewer:" — strip it.
    text = re.sub(r"^\s*(interviewer|assistant)\s*:\s*", "", text, flags=re.IGNORECASE)
    return text.strip()


PROFILE_SYSTEM = (
    "You read a candidate's resume and extract a structured professional profile. "
    "You are domain-agnostic — the candidate may be a software engineer, teacher, nurse, "
    "marketer, accountant, designer, lawyer, or any other professional. "
    "Return ONLY raw JSON — no markdown, no backticks, no commentary."
)


def build_profile_prompt(resume_text: str) -> str:
    return f"""Read the following resume and extract a structured profile.

RESUME:
\"\"\"
{resume_text[:5000]}
\"\"\"

Return ONLY a JSON object with EXACTLY these fields:
{{
  "domain": "<the candidate's primary professional domain — e.g. Software Engineering, Education, Healthcare, Marketing, Finance, Law, Design, Sales, Human Resources, Operations, Data Science, Product Management, Research, Mechanical Engineering, etc.>",
  "roles": ["<their current or most recent job title>", "<a second relevant title if any>"],
  "yearsOfExperience": <integer estimate from earliest job to now, 0 if fresher>,
  "experienceLevel": "fresher" | "junior" | "mid" | "senior" | "expert",
  "isTechnical": <true if the role requires writing code, building software, or working hands-on with technical systems; false for teaching, healthcare, marketing, HR, sales, etc.>,
  "topSkills": ["<skill1>", "<skill2>", "<skill3>", "<skill4>", "<skill5>"],
  "notableProjects": ["<project1>", "<project2>"]
}}

Rules:
- experienceLevel mapping: 0-1 yrs = fresher, 1-3 = junior, 3-7 = mid, 7-15 = senior, 15+ = expert
- domain must reflect what they ACTUALLY do, not the field of their degree
- isTechnical is true ONLY for roles like software engineer, devops, data engineer, embedded systems, etc.
- A teacher of computer science is isTechnical = false (they teach, not build)
- Use the candidate's own words for skills where possible
- Return valid JSON only — no extra text.
"""


async def extract_profile_from_resume(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    resume_text: str,
) -> dict:
    """Run a single LLM call to extract a domain-aware profile from the resume."""
    resolved_key = resolve_api_key(provider, api_key)
    text = await _call_chat_text_with_fallback(
        client, provider, resolved_key, model,
        system=PROFILE_SYSTEM,
        messages=[{"role": "user", "content": build_profile_prompt(resume_text)}],
        temperature=0.2,
        max_tokens=768,
        label="profile",
    )
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ProviderResponseError(f"No JSON in profile response: {repr(text[:150])}")
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as error:
        raise ProviderResponseError(f"Could not parse profile JSON: {error.msg}") from error

    valid_levels = ("fresher", "junior", "mid", "senior", "expert")
    level = data.get("experienceLevel")
    if level not in valid_levels:
        years = int(data.get("yearsOfExperience") or 0)
        if years < 1:
            level = "fresher"
        elif years < 3:
            level = "junior"
        elif years < 7:
            level = "mid"
        elif years < 15:
            level = "senior"
        else:
            level = "expert"

    return {
        "domain": str(data.get("domain") or "General Professional").strip(),
        "roles": [str(r).strip() for r in (data.get("roles") or []) if isinstance(r, (str, int)) and str(r).strip()][:3] or ["Professional"],
        "yearsOfExperience": int(data.get("yearsOfExperience") or 0),
        "experienceLevel": level,
        "isTechnical": bool(data.get("isTechnical", True)),
        "topSkills": [str(s).strip() for s in (data.get("topSkills") or []) if isinstance(s, (str, int)) and str(s).strip()][:8],
        "notableProjects": [str(p).strip() for p in (data.get("notableProjects") or []) if isinstance(p, (str, int)) and str(p).strip()][:5],
    }


# ─── Domain-aware evaluation criteria ────────────────────

DOMAIN_CRITERIA: dict[str, str] = {
    "education": (
        "- Does the answer show understanding of pedagogy or teaching methods?\n"
        "- Does it mention student outcomes, engagement, learning goals, or classroom management?\n"
        "- Reward: Bloom's Taxonomy, differentiated instruction, formative assessment, lesson planning, "
        "student-centered learning, parent communication."
    ),
    "healthcare": (
        "- Does the answer reflect patient-centered thinking and clinical accuracy for their role?\n"
        "- Does it mention protocols, safety, or patient outcomes?\n"
        "- Reward: empathy, accuracy, safety-first mindset, team coordination, evidence-based practice."
    ),
    "marketing": (
        "- Does the answer show strategic thinking about audience, channels, and goals?\n"
        "- Does it reference metrics, campaigns, brand awareness, or the marketing funnel?\n"
        "- Reward: ROI thinking, data-driven decisions, creativity, channel knowledge."
    ),
    "human resources": (
        "- Does the answer reflect knowledge of HR policies, people management, and fairness?\n"
        "- Does it show empathy, conflict resolution, and organisational awareness?\n"
        "- Reward: policy knowledge, culture building, structured processes."
    ),
    "sales": (
        "- Does the answer show understanding of pipeline, objection handling, and customer needs?\n"
        "- Does it reference quotas, qualification frameworks (BANT, MEDDIC), or relationship building?\n"
        "- Reward: empathy, persistence, data-driven follow-up."
    ),
    "finance": (
        "- Does the answer show numerical accuracy and an understanding of financial principles?\n"
        "- Does it reference reporting standards, controls, or risk?\n"
        "- Reward: precision, regulatory awareness, business impact."
    ),
    "design": (
        "- Does the answer show user-centred thinking and visual / interaction craft?\n"
        "- Does it reference research, accessibility, design systems, or trade-offs?\n"
        "- Reward: empathy for users, iteration, critique culture."
    ),
}


def _domain_criteria(domain: str, is_technical: bool) -> str:
    key = (domain or "").strip().lower()
    if key in DOMAIN_CRITERIA:
        return DOMAIN_CRITERIA[key]
    if is_technical:
        return (
            "- Does the answer correctly address the technical concept?\n"
            "- Is the explanation clear, accurate, and grounded in real practice?\n"
            "- Reward: real examples, trade-off awareness, best practices, performance / scaling considerations."
        )
    return (
        f"- Does the answer directly address the question asked within the {domain} field?\n"
        f"- Does it show real domain knowledge and practical experience as a professional in {domain}?\n"
        f"- Is the answer coherent and professionally expressed?\n"
        f"- Reward any answer that shows genuine understanding of the candidate's field."
    )


LENIENCY_BY_LEVEL: dict[str, str] = {
    "fresher": (
        "Be very lenient — they are starting out.\n"
        "- Incomplete answers = partial (not incorrect)\n"
        "- An honest 'I don't know but I'd learn X' = partial credit\n"
        "- Do not require examples from work experience\n"
        "- Reward curiosity and willingness to learn."
    ),
    "junior": (
        "Be moderately lenient — they have basic experience.\n"
        "- Correct concept with vague example = partial\n"
        "- Correct concept with clear example = correct\n"
        "- Partial answers are fine if direction is correct."
    ),
    "mid": (
        "Be balanced — expect practical knowledge.\n"
        "- Must show real-world application, not just theory\n"
        "- Vague answers without examples = partial\n"
        "- Clear example with one trade-off = correct."
    ),
    "senior": (
        "Apply a high standard — expect depth and leadership.\n"
        "- Textbook answers without context = partial\n"
        "- Must show decision-making and trade-off awareness\n"
        "- No examples from experience = mark down."
    ),
    "expert": (
        "Apply a very high standard — strategic and systemic thinking expected.\n"
        "- Surface-level answers = incorrect\n"
        "- Must show organisational or industry-level thinking."
    ),
}


def build_role_aware_eval_prompt(section: str, question: str, answer: str, profile: dict | None) -> str:
    """Build an evaluation prompt that adapts to the candidate's domain and level."""
    if not profile:
        # Fall back to the original technical-only prompt for catalogue questions
        return build_eval_prompt(section, question, answer)

    domain = profile.get("domain") or "General Professional"
    role = (profile.get("roles") or ["Professional"])[0]
    level = profile.get("experienceLevel") or "mid"
    years = profile.get("yearsOfExperience") or 0
    is_tech = bool(profile.get("isTechnical", True))
    criteria = _domain_criteria(domain, is_tech)
    leniency = LENIENCY_BY_LEVEL.get(level, LENIENCY_BY_LEVEL["mid"])

    return f"""You are a fair and experienced {domain} professional evaluating a job interview answer.

=== CANDIDATE CONTEXT ===
Domain:           {domain}
Role:             {role}
Experience level: {level} ({years} yrs)
Is technical:     {is_tech}

=== SECTION ===
{section}

=== QUESTION ASKED ===
{question}

=== CANDIDATE'S ANSWER ===
{answer}

=== HOW TO EVALUATE ===
{criteria}

=== LENIENCY GUIDE ===
{leniency}

=== CRITICAL RULES ===
- NEVER judge a {domain} answer using software/coding standards (unless isTechnical is true).
- A teacher mentioning "Bloom's Taxonomy" or "differentiated instruction" = CORRECT.
- A teacher NOT knowing JavaScript = completely NORMAL and NOT a mistake.
- A fresher giving an incomplete but directionally correct answer = PARTIAL, not INCORRECT.
- Only mark "incorrect" if the answer is completely irrelevant OR blank.
- Feedback must use {domain} terminology, not tech jargon.
- "ideal" must sound like a real {role} would say it.
- Judge this answer as a {level} {role}, NOT as a software engineer.

EVALUATION INSTRUCTIONS:
1. SEMANTIC INTERPRETATION: First, mentally correct any obvious voice transcription errors in the answer. Evaluate the corrected meaning.
2. CONCEPT EXTRACTION: Identify the 3-5 key things this question requires. For each, decide if the candidate demonstrated understanding (even partially).
3. SCORING RUBRIC (apply leniency for the candidate's level above):
   - 85-100 (correct): Covers all key points accurately for a {level} {role}, even if not perfectly worded
   - 50-84 (partial): Demonstrates clear understanding of some points but misses others
   - 20-49 (partial): Shows awareness of the topic but with significant gaps
   - 0-19 (incorrect): Does not demonstrate meaningful understanding or is irrelevant/blank
4. VERDICT RULES:
   - "correct" if score >= 75
   - "partial" if score >= 30
   - "incorrect" if score < 30

Respond with ONLY a raw JSON object — no markdown, no backticks, no explanation outside the JSON:
{{"score": <integer 0-100>, "verdict": "correct"|"partial"|"incorrect", "strength": "<specific things they demonstrated correctly in {domain} terms — be generous with partial credit>", "missing": "<specific {domain}-relevant points they missed — be precise>", "hint": "<Socratic question pointing toward the gap, empty string if correct>", "ideal": "<concise ideal answer in 2-3 sentences, phrased as a real {role} would say it>"}}"""


EXTRACT_SYSTEM = (
    "You analyse a candidate's interview answer and extract structured insights. "
    "Return ONLY raw JSON — no markdown, no backticks, no commentary."
)


def build_extract_prompt(answer: str, state: dict) -> str:
    known = ", ".join(state.get("extractedSkills", [])) or "none"
    return f"""Analyse this interview answer and extract structured information.

Already-known skills: {known}
Current phase: {state.get('phase', 'introduction')}
Current difficulty (1-3): {state.get('difficultyLevel', 1)}

Answer:
\"\"\"
{answer}
\"\"\"

Return ONLY a JSON object with this exact shape:
{{
  "newSkills": ["skill1", "skill2"],
  "newProjects": ["project1"],
  "answerQuality": "weak" | "average" | "strong",
  "confidence": "low" | "medium" | "high",
  "suggestedNextPhase": "introduction" | "project_deep_dive" | "skill_basic" | "skill_intermediate" | "skill_advanced" | "wrap_up"
}}

Rules:
- newSkills must NOT include any already-known skills.
- answerQuality is "strong" if the answer is detailed, technically accurate, and shows depth.
- answerQuality is "weak" if the answer is short, vague, off-topic, or wrong.
- suggestedNextPhase must progress logically from the current phase based on questionCount and quality.
"""


async def extract_insights_from_answer(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    answer: str,
    state: dict,
) -> dict:
    """Run a lightweight LLM call to extract skills/projects/quality from an answer."""
    resolved_key = resolve_api_key(provider, api_key)
    prompt = build_extract_prompt(answer, state)
    text = await _call_chat_text_with_fallback(
        client, provider, resolved_key, model,
        system=EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=512,
        label="extract",
    )
    # Tolerant JSON extraction
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ProviderResponseError(f"No JSON in extract response: {repr(text[:150])}")
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as error:
        raise ProviderResponseError(f"Could not parse extract JSON: {error.msg}") from error

    return {
        "newSkills": [str(s) for s in (data.get("newSkills") or []) if isinstance(s, str)],
        "newProjects": [str(p) for p in (data.get("newProjects") or []) if isinstance(p, str)],
        "answerQuality": data.get("answerQuality") if data.get("answerQuality") in ("weak", "average", "strong") else "average",
        "confidence": data.get("confidence") if data.get("confidence") in ("low", "medium", "high") else "medium",
        "suggestedNextPhase": data.get("suggestedNextPhase") if data.get("suggestedNextPhase") in (
            "introduction", "project_deep_dive", "skill_basic", "skill_intermediate", "skill_advanced", "wrap_up"
        ) else None,
    }
