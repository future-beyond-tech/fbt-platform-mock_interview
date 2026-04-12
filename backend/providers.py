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
from datetime import datetime
from typing import Any, Awaitable, Callable

import httpx


def _log(*args, **kwargs):
    """Print with an ISO timestamp prefix. Preserves the caller's stream."""
    ts = datetime.now().isoformat(timespec="seconds")
    print(f"[{ts}]", *args, **kwargs)

# ─── Retry + provider fallback ────────────────────────────
# Transient HTTP statuses worth retrying. 503 is the Google AI Studio
# "high demand" overload code; 529 is Anthropic's overload; 500/502/504 are
# generic transient gateway errors.
RETRY_STATUSES: set[int] = {429, 500, 502, 503, 504, 529}

# Provider circuit-breaker: when a provider returns an overload status, mark
# it "sick" for COOLDOWN_SECONDS. Subsequent calls within that window short-
# circuit their retry chain and raise immediately so the fallback path runs
# without waiting. This prevents the "two back-to-back LLM calls each pay
# the full Gemini retry cost" problem on endpoints like /interview/start.
OVERLOAD_COOLDOWN_SECONDS: float = 60.0
_provider_cooldown: dict[str, float] = {}


def _provider_sick(provider: str) -> bool:
    deadline = _provider_cooldown.get(provider)
    if deadline is None:
        return False
    if asyncio.get_event_loop().time() >= deadline:
        _provider_cooldown.pop(provider, None)
        return False
    return True


def _mark_provider_sick(provider: str) -> None:
    _provider_cooldown[provider] = asyncio.get_event_loop().time() + OVERLOAD_COOLDOWN_SECONDS
    _log(
        f"[circuit-breaker] {provider} marked sick for {OVERLOAD_COOLDOWN_SECONDS:.0f}s; "
        f"next calls will skip straight to fallback",
        file=sys.stderr,
    )


async def _retry_with_backoff(
    fn: Callable[[], Awaitable[Any]],
    *,
    max_attempts: int = 2,
    base_delay: float = 0.3,
    max_delay: float = 2.0,
    label: str = "call",
    provider: str | None = None,
) -> Any:
    """Run `fn`, retrying on transient HTTP errors with exponential backoff.

    If `provider` is given and is currently under overload cooldown, raise
    immediately so the caller can fall back without paying the retry cost.
    """
    if provider and _provider_sick(provider):
        _log(
            f"[retry:{label}] skipping — {provider} is under overload cooldown",
            file=sys.stderr,
        )
        # Raise a synthetic 503 so the fallback branch in the caller runs.
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
                    _mark_provider_sick(provider)
                raise
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            _log(
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
            _log(
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
    "You are a senior technical interviewer. Evaluate SEMANTICALLY — intent and knowledge, not perfect phrasing. "
    "Voice-to-text errors should be read charitably (e.g. 'letten' → 'let and', 'ESG' → 'ES6'). "
    "Feedback must sound like a senior peer who redirects without blame: never say wrong, failed, or nonsensical about the person. "
    "Judge what the candidate KNOWS."
)


def _truncate_words(s: str, max_words: int) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    words = s.split()
    if len(words) <= max_words:
        return s
    return " ".join(words[:max_words])


def _gaps_from_missing(missing: str) -> list[str]:
    if not missing or not str(missing).strip():
        return []
    m = str(missing).strip()
    if m.lower() == "none":
        return []
    if "|||" in m:
        parts = [p.strip() for p in m.split("|||")]
    elif "\n" in m:
        parts = [p.strip() for p in m.split("\n") if p.strip()]
    elif " · " in m:
        parts = [p.strip() for p in m.split(" · ")]
    else:
        parts = [m]
    out: list[str] = []
    for p in parts:
        if p and p.lower() != "none":
            t = _truncate_words(p, 8)
            if t:
                out.append(t)
        if len(out) >= 2:
            break
    return out[:2]


def _normalize_gaps_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        t = _truncate_words(item, 8)
        if t and t.lower() != "none":
            out.append(t)
        if len(out) >= 2:
            break
    return out


def build_eval_prompt(section: str, question: str, answer: str) -> str:
    return f"""Section: {section}
Question: {question}
Candidate answer: {answer}

EVALUATION INSTRUCTIONS:
1. SEMANTIC INTERPRETATION: Mentally correct obvious voice transcription errors, then evaluate meaning.
2. CONCEPT EXTRACTION: Identify 3–5 key concepts this question requires; note what the answer demonstrated.
3. SCORING RUBRIC:
   - 85-100 (correct): Covers key concepts accurately
   - 50-84 (partial): Clear understanding of some concepts, misses others
   - 20-49 (partial): Awareness with significant gaps
   - 0-19 (incorrect): No meaningful understanding of core concepts
4. VERDICT: "correct" if score >= 75; "partial" if score >= 30; "incorrect" if score < 30

FEEDBACK VOICE (senior peer — concise coaching card):
- strength: ONE line, max 6 words, genuine signal only. Use "" if nothing real to affirm — forbid filler phrases like "Attempted", "Tried", "Managed to".
- gaps: JSON array of 0–2 strings. Each max 8 words — neutral description of the gap (what was thin or absent), not blame. Use [] if nothing material.
- missing: Same content as gaps joined with " · " (for legacy clients).
- hint: Coaching redirect for next time, max 12 words — NOT a question. Do NOT start with "You should", "You need to", "You must". Use "" when there is nothing to add.
- ideal: Max 3 sentences, first person, natural strong answer (not labeled perfect or correct).

Respond with ONLY a raw JSON object — no markdown, no backticks, no explanation outside the JSON:
{{"score": <integer 0-100>, "verdict": "correct"|"partial"|"incorrect", "strength": "<string>", "gaps": ["<optional>", "<optional>"], "missing": "<string>", "hint": "<string>", "ideal": "<string>"}}"""


def parse_eval_json(text: str) -> dict | None:
    """Extract evaluation JSON from any LLM output."""
    import sys
    if not text or not text.strip():
        _log(f"[parse_eval_json] Empty text received", file=sys.stderr)
        return None

    # Remove markdown fences and leading/trailing whitespace
    cleaned = re.sub(r"```(?:json)?```?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()

    # Find outermost JSON object
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        _log(f"[parse_eval_json] No JSON object found. Raw text (200 chars): {repr(text[:200])}", file=sys.stderr)
        return None

    json_str = cleaned[start : end + 1]
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        _log(f"[parse_eval_json] JSON parse error: {e}. Snippet: {repr(json_str[:200])}", file=sys.stderr)
        return None

    if "score" not in data or "verdict" not in data:
        _log(f"[parse_eval_json] Missing required fields. Got keys: {list(data.keys())}", file=sys.stderr)
        return None

    score = max(0, min(100, int(data.get("score", 0))))
    verdict = data.get("verdict", "incorrect")
    if verdict not in ("correct", "partial", "incorrect"):
        verdict = "incorrect"

    strength = _truncate_words(str(data.get("strength", "")), 6)
    missing_raw = str(data.get("missing", ""))
    hint = _truncate_words(str(data.get("hint", "")), 12)
    ideal = str(data.get("ideal", ""))[:1000]

    gaps = _normalize_gaps_list(data.get("gaps"))
    if not gaps:
        gaps = _gaps_from_missing(missing_raw)

    missing_lower = missing_raw.strip().lower()
    if gaps:
        missing_out = " · ".join(gaps)[:500]
    elif missing_lower and missing_lower != "none":
        missing_out = missing_raw.strip()[:500]
    else:
        missing_out = ""

    return {
        "score": score,
        "verdict": verdict,
        "strength": strength[:500],
        "missing": missing_out,
        "gaps": gaps,
        "hint": hint[:500],
        "ideal": ideal,
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
        _log(f"[Gemini] No candidates in response: {data}", file=sys.stderr)
        raise ProviderResponseError("Gemini returned no candidates")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if p.get("text"))
    _log(f"[Gemini] Raw text (200): {repr(text[:200])}", file=sys.stderr)
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
            "model": model or "llama-3.1-8b-instant",
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
        return await _retry_with_backoff(_primary, label=f"eval:{provider}", provider=provider)
    except (httpx.HTTPStatusError, httpx.RequestError) as primary_error:
        if provider == "ollama":
            raise

        # Build eval fallback chain.
        fallbacks: list[tuple[str, str, str]] = []  # (label, provider, model)
        if provider != "gemini":
            try:
                resolve_api_key("gemini", "")
                fallbacks.append(("gemini-flash", "gemini", "gemini-2.0-flash"))
            except ClientInputError:
                pass
        if provider != "groq":
            try:
                resolve_api_key("groq", "")
                fallbacks.append(("groq", "groq", GROQ_FALLBACK_MODEL))
            except ClientInputError:
                pass

        if not fallbacks:
            raise primary_error

        for fb_label, fb_provider, fb_model in fallbacks:
            _log(
                f"[fallback:eval] {provider} exhausted; trying {fb_label} ({fb_model})",
                file=sys.stderr,
            )

            async def _make_fb(p=fb_provider, m=fb_model) -> dict:
                return await _evaluate_once(
                    client, p, "", m, section, question, answer, profile,
                )

            try:
                return await _retry_with_backoff(
                    _make_fb, max_attempts=2,
                    label=f"eval:{fb_label}", provider=fb_provider,
                )
            except Exception as fb_error:
                _log(f"[fallback:eval] {fb_label} also failed: {fb_error}", file=sys.stderr)
                continue

        raise primary_error


# ─── Follow-up question (partial answers) ─────────────────

FOLLOWUP_GEN_SYSTEM = (
    "You are a senior interviewer. Your job is to ask ONE short spoken question that pins down "
    "something unclear in the candidate's own words—not a new textbook question on the topic. "
    "Output only that question: one line, no preamble, no label like 'Follow-up:', no numbering, no quotes around the whole line."
)

FOLLOWUP_EVAL_SYSTEM = (
    "You judge whether a candidate's follow-up answer shows they understood the concept. "
    "Respond with ONLY valid JSON, no markdown."
)

_TIER_CONTEXT_LABELS = {
    "tier_1": "Tier 1 · Foundations",
    "tier_2": "Tier 2 · Advanced",
    "tier_3": "Tier 3 · Expert",
}


def _tier_context_line(topic: str) -> str:
    t = (topic or "").strip()
    if not t:
        return ""
    label = _TIER_CONTEXT_LABELS.get(t, t.replace("_", " "))
    return (
        f"Depth band (terminology/tone only — do NOT ask a generic question on this band; anchor on their answer): {label}\n"
    )


def _profile_context_line(profile: dict | None) -> str:
    if not profile:
        return ""
    domain = str(profile.get("domain") or "").strip()
    if not domain:
        return ""
    return f"Domain (appropriate vocabulary only — still anchor the question on their words): {domain}\n"


def build_followup_generate_prompt(
    original_question: str,
    user_answer: str,
    topic: str,
    profile: dict | None = None,
) -> str:
    tier_line = _tier_context_line(topic)
    profile_line = _profile_context_line(profile)
    ua = (user_answer or "").strip()
    if not ua:
        return f"""Original Question: {original_question}

The candidate gave no substantive answer.

Ask ONE concise question that invites them to answer the original question with one concrete example.
Return ONLY the question text, nothing else."""

    return f"""Original interview question:
{original_question}

{tier_line}{profile_line}Candidate's answer (this is the primary text to analyze — quote or paraphrase from here):
{user_answer}

Instructions:
1. Internally, identify ONE phrase, claim, example, or step in their answer that is vague, under-specified, hand-wavy, or needs justification (e.g. undefined term, missing mechanism, unclear "how/why").
2. Output exactly ONE spoken question that targets THAT fragment — e.g. "You mentioned ___ — can you walk through how that works in your case?" or "When you said ___, what did you mean by ___?"
3. Do NOT ask a fresh definition question about the topic if their answer already names the topic — drill into what THEY said.
4. Do NOT repeat the original question verbatim.
5. Keep it answerable in about 30–60 seconds verbally.

Return ONLY the question text, nothing else."""


def _strip_followup_question(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    t = re.sub(r'^["\']|["\']$', "", t.strip())
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if not lines:
        return ""
    return lines[0][:500]


def build_followup_eval_prompt(original_question: str, follow_up_question: str, answer: str) -> str:
    return f"""Original interview question: {original_question}

Follow-up question asked: {follow_up_question}

Candidate's follow-up answer: {answer}

Did the candidate demonstrate clear understanding in this follow-up (substantive, correct, on-topic)?

Respond with ONLY a raw JSON object — no markdown, no backticks:
{{"clarified": true or false, "feedback": "<one short sentence>"}}"""


def parse_followup_eval_json(text: str) -> dict | None:
    if not text or not text.strip():
        return None
    cleaned = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    if "clarified" not in data:
        return None
    clarified = bool(data.get("clarified"))
    feedback = str(data.get("feedback", ""))[:300]
    return {"clarified": clarified, "feedback": feedback}


async def generate_followup_question_with_provider(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    original_question: str,
    user_answer: str,
    topic: str = "",
    profile: dict | None = None,
) -> str:
    resolved_key = ""
    if provider != "ollama":
        resolved_key = resolve_api_key(provider, api_key)
    prompt = build_followup_generate_prompt(original_question, user_answer, topic, profile)
    text = await _call_chat_text_with_fallback(
        client,
        provider,
        resolved_key,
        model,
        FOLLOWUP_GEN_SYSTEM,
        [{"role": "user", "content": prompt}],
        temperature=0.45,
        max_tokens=220,
        label="followup-gen",
    )
    return _strip_followup_question(text) or (
        "You touched on several points — pick one sentence from your answer and unpack it: what did you mean, and how did it play out in practice?"
    )


async def evaluate_followup_with_provider(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    original_question: str,
    follow_up_question: str,
    answer: str,
    profile: dict | None = None,
) -> dict:
    resolved_key = ""
    if provider != "ollama":
        resolved_key = resolve_api_key(provider, api_key)
    prompt = build_followup_eval_prompt(original_question, follow_up_question, answer)
    text = await _call_chat_text_with_fallback(
        client,
        provider,
        resolved_key,
        model,
        FOLLOWUP_EVAL_SYSTEM,
        [{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=256,
        label="followup-eval",
    )
    parsed = parse_followup_eval_json(text)
    if not parsed:
        raise ProviderResponseError("Follow-up evaluation returned unparseable output")
    return parsed


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
            mdl = model or "llama-3.1-8b-instant"
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

    _log(f"[gen] raw (len={len(text)}): {repr(text[:400])}", file=sys.stderr)

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

        _log(f"[file-vision] raw (200): {repr(text[:200])}", file=sys.stderr)
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
GROQ_FALLBACK_MODEL = "llama-3.1-8b-instant"  # higher free-tier limit than 70b


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
        return await _retry_with_backoff(_primary, label=f"{label}:{provider}", provider=provider)
    except (httpx.HTTPStatusError, httpx.RequestError) as primary_error:
        # Build a fallback chain: try alternative providers in order.
        fallbacks: list[tuple[str, str, str, str]] = []  # (label, provider, key, model)

        # Fallback 1: Gemini flash (if primary wasn't already Gemini).
        if provider != "gemini":
            try:
                gemini_key = resolve_api_key("gemini", "")
                fallbacks.append(("gemini-flash", "gemini", gemini_key, "gemini-2.0-flash"))
            except ClientInputError:
                pass

        # Fallback 2: Groq (if primary wasn't already Groq).
        if provider != "groq":
            try:
                groq_key = resolve_api_key("groq", "")
                fallbacks.append(("groq", "groq", groq_key, GROQ_FALLBACK_MODEL))
            except ClientInputError:
                pass

        if not fallbacks:
            _log(
                f"[fallback:{label}] {provider} exhausted retries and no fallback keys available",
                file=sys.stderr,
            )
            raise primary_error

        for fb_label, fb_provider, fb_key, fb_model in fallbacks:
            _log(
                f"[fallback:{label}] {provider} exhausted; trying {fb_label} ({fb_model})",
                file=sys.stderr,
            )

            async def _make_fallback(p=fb_provider, k=fb_key, m=fb_model) -> str:
                return await _call_chat_text(
                    client, p, k, m, system, messages,
                    temperature=temperature, max_tokens=max_tokens,
                )

            try:
                return await _retry_with_backoff(
                    _make_fallback, max_attempts=2,
                    label=f"{label}:{fb_label}", provider=fb_provider,
                )
            except Exception as fb_error:
                _log(
                    f"[fallback:{label}] {fb_label} also failed: {fb_error}",
                    file=sys.stderr,
                )
                continue

        # All fallbacks exhausted.
        raise primary_error


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


# ─── Structured 12-question interview with Knowledge Ladder ──

# Session flow: position → (type, source)
SESSION_FLOW: list[tuple[str, str]] = [
    # (type,              source)
    ("intro",             "fixed"),       # Q1
    ("resume_overview",   "fixed"),       # Q2
    ("tier_1",            "ladder"),      # Q3  — Foundational
    ("tier_1",            "ladder"),      # Q4  — Foundational
    ("project_based",     "resume"),      # Q5
    ("tier_2",            "ladder"),      # Q6  — Advanced
    ("tier_2",            "ladder"),      # Q7  — Advanced
    ("behavioral",        "dynamic"),     # Q8
    ("tier_2",            "ladder"),      # Q9  — Advanced
    ("tier_3",            "ladder"),      # Q10 — Expert Practical
    ("tier_3",            "ladder"),      # Q11 — Expert Practical
    ("wrap",              "fixed"),       # Q12
]


CATEGORY_LABELS: dict[str, str] = {
    "intro": "Introduction",
    "resume_overview": "Career Overview",
    "tier_1": "Tier 1 · Foundations",
    "tier_2": "Tier 2 · Advanced",
    "tier_3": "Tier 3 · Expert",
    "project_based": "Project Deep Dive",
    "behavioral": "Behavioral",
    "wrap": "Wrap Up",
}


_INTRO_QUESTIONS = [
    "Tell me about yourself — walk me through your background, what you've been working on, and what brings you here today.",
    "Start us off by giving me a quick overview of who you are, your career so far, and what you're looking for next.",
    "In your own words, describe your professional journey — what got you into this field and where you are now.",
    "Give me the highlight reel of your career: where you started, what you've built, and what excites you about your next move.",
    "Walk me through your background — your experience, what you've been focused on recently, and why you're here.",
    "Before we dive in, tell me a bit about yourself — your path, your current role, and what brought you to this conversation.",
    "Let's start with you — tell me about your experience, what kind of work you enjoy most, and what you're looking to do next.",
]

_WRAP_QUESTIONS = [
    "That wraps up my questions. Do you have anything you'd like to ask me, or is there anything about your experience you feel we didn't get to cover?",
    "We're coming to the end of our time — is there anything you'd like to ask, or something important about yourself you'd like to add?",
    "Before we finish, do you have any questions for me? And is there anything you feel didn't come up that you'd want me to know?",
    "That's all from my side. What questions do you have, and is there anything you'd like to clarify or expand on?",
    "We've covered a lot of ground — any questions on your end? And is there something you feel would be important for us to discuss before we wrap up?",
    "Last question: what would you like to ask me? Also, is there anything about your background or skills we didn't touch on that you'd like to highlight?",
    "That brings us to a close. Do you have any questions, or is there anything you'd like to revisit from earlier in our conversation?",
]


def get_intro_question() -> dict:
    import random
    return {
        "question": random.choice(_INTRO_QUESTIONS),
        "topic": "introduction",
        "category": "intro",
        "difficulty": "easy",
        "what_to_evaluate": "Communication clarity, career narrative, confidence, and relevance.",
    }


def get_wrap_question() -> dict:
    import random
    return {
        "question": random.choice(_WRAP_QUESTIONS),
        "topic": "wrap_up",
        "category": "wrap",
        "difficulty": "easy",
        "what_to_evaluate": "Curiosity, self-awareness, and ability to advocate for themselves.",
    }


# ── Knowledge Ladder generation ──

KNOWLEDGE_LADDER_SYSTEM = (
    "You are an expert curriculum designer and senior interviewer. "
    "Return ONLY raw JSON — no markdown, no backticks, no commentary."
)


def build_knowledge_ladder_prompt(resume_text: str, blueprint: dict) -> str:
    skills = ", ".join(blueprint.get("core_skills") or []) or "N/A"
    return f"""Analyse this candidate's resume and generate a PROGRESSIVE KNOWLEDGE LADDER
for their interview. The ladder must go from foundational → advanced → practical.

RESUME:
\"\"\"
{resume_text[:4000]}
\"\"\"

SENIORITY LEVEL: {blueprint.get('seniority_level', 'mid')}
PRIMARY DOMAIN: {blueprint.get('primary_domain', 'General')}
CORE SKILLS: {skills}

Generate a knowledge ladder with exactly 3 tiers.
Each tier has 4-5 specific topics to test.
Topics must be:
  - Specific to their domain (not generic)
  - Progressive — each tier harder than the last
  - Mix of theory AND practical application
  - Completely independent of their resume content (test knowledge, not just what they've done)

Return JSON only:
{{
  "tier_1": {{
    "level": "foundational",
    "label": "Core Fundamentals",
    "description": "Basic definitions, terminology, core concepts",
    "topics": [
      {{"topic": "...", "depth": "...", "sample_question_angle": "..."}}
    ]
  }},
  "tier_2": {{
    "level": "advanced",
    "label": "Advanced Concepts",
    "description": "How and why things work, tradeoffs, design decisions",
    "topics": [
      {{"topic": "...", "depth": "...", "sample_question_angle": "..."}}
    ]
  }},
  "tier_3": {{
    "level": "expert_practical",
    "label": "Real-World Problem Solving",
    "description": "Complex scenarios, debugging, architecture, scale",
    "topics": [
      {{"topic": "...", "depth": "...", "sample_question_angle": "..."}}
    ]
  }}
}}"""


async def generate_knowledge_ladder(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    resume_text: str,
    blueprint: dict,
) -> dict:
    """Generate a 3-tier knowledge ladder from the resume."""
    resolved_key = resolve_api_key(provider, api_key)
    text = await _call_chat_text_with_fallback(
        client, provider, resolved_key, model,
        system=KNOWLEDGE_LADDER_SYSTEM,
        messages=[{"role": "user", "content": build_knowledge_ladder_prompt(resume_text, blueprint)}],
        temperature=0.2,
        max_tokens=1536,
        label="ladder",
    )
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ProviderResponseError(f"No JSON in ladder response: {repr(text[:150])}")
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as error:
        raise ProviderResponseError(f"Could not parse ladder JSON: {error.msg}") from error

    # Normalise each tier.
    result = {}
    for tier_key in ("tier_1", "tier_2", "tier_3"):
        tier = data.get(tier_key) or {}
        topics = []
        for t in (tier.get("topics") or [])[:5]:
            if isinstance(t, dict) and t.get("topic"):
                topics.append({
                    "topic": str(t["topic"]).strip(),
                    "depth": str(t.get("depth", "")).strip(),
                    "sample_question_angle": str(t.get("sample_question_angle", "")).strip(),
                })
        result[tier_key] = {
            "level": str(tier.get("level", tier_key)).strip(),
            "label": str(tier.get("label", tier_key)).strip(),
            "description": str(tier.get("description", "")).strip(),
            "topics": topics,
        }
    return result


# ── Question generators for each source type ──

STRUCTURED_Q_SYSTEM = (
    "You are a senior interviewer conducting a structured mock interview. "
    "Return ONLY a raw JSON object — no markdown, no backticks, no explanation. "
    "CRITICAL: The 'question' field must be a SHORT, conversational interview question — "
    "1-3 sentences MAX (under 50 words). Ask ONE focused thing. "
    "Never write essay-style prompts, multi-part assignments, or paragraphs. "
    "Think about how a real interviewer speaks across a table: brief, clear, direct."
)


def _parse_question_json(text: str, fallback_category: str) -> dict:
    """Parse a JSON question from LLM output, with a graceful fallback."""
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    fallback = {
        "question": text.strip(),
        "topic": fallback_category,
        "category": fallback_category,
        "difficulty": "medium",
        "what_to_evaluate": "",
    }
    if start == -1 or end <= start:
        return fallback
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return fallback
    return {
        "question": str(data.get("question", text)).strip(),
        "topic": str(data.get("topic", fallback_category)).strip(),
        "category": str(data.get("category", fallback_category)).strip(),
        "difficulty": str(data.get("difficulty", "medium")).strip(),
        "what_to_evaluate": str(data.get("what_to_evaluate", "")).strip(),
    }


async def _generate_ladder_question(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    blueprint: dict,
    ladder: dict,
    tier_key: str,
    topic_index: int,
    session_state: dict,
) -> dict:
    """Generate one question from a specific tier of the knowledge ladder."""
    import random

    tier = ladder.get(tier_key, {})
    topics = tier.get("topics") or []
    if not topics:
        return {
            "question": f"Tell me about a core concept in {blueprint.get('primary_domain', 'your field')} that you find most important in practice.",
            "topic": tier_key,
            "category": tier_key,
            "difficulty": "medium",
            "what_to_evaluate": "Domain knowledge depth",
        }

    asked_topics = session_state.get("askedTopics") or []
    # Shuffle untested topics so each session gets a different order.
    untested = [t for t in topics if t["topic"] not in asked_topics]
    if untested:
        random.shuffle(untested)
        topic = untested[0]
    else:
        topic = random.choice(topics)

    asked_qs = session_state.get("questionsAsked") or []
    primary_lang = blueprint.get("primary_language_or_tool") or ""
    stack = ", ".join(blueprint.get("frameworks_and_stack") or []) or "N/A"
    subject = blueprint.get("subject_specialization") or blueprint.get("primary_domain") or "their field"
    role_type = blueprint.get("role_type") or "professional"
    tier_focus = tier.get("focus") or tier.get("description") or ""

    prompt = f"""You are a senior interviewer testing a {role_type}.

CANDIDATE:
- Domain: {blueprint.get('primary_domain', 'General')}
- Subject Specialization: {subject}
- Seniority: {blueprint.get('seniority_level', 'mid')} ({blueprint.get('experience_years', 0)} yrs)
- Stack: {stack}

TOPIC TO TEST: "{topic['topic']}"
TIER: {tier.get('label', tier_key)}
{f'TIER FOCUS: {tier_focus}' if tier_focus else ''}

Generate a SPECIFIC question about "{topic['topic']}" in {subject}.

CRITICAL: Keep the question SHORT — 1-3 sentences, under 50 words. Ask ONE focused thing like a real interviewer.

TIER RULES:
- Tier 1 (Fundamentals): "what is", "explain", "difference between" — test SUBJECT knowledge only
  Physics: "Explain Newton's Third Law with two real-world examples."
  React: "What is the difference between var, let, and const?"

- Tier 2 (Advanced): "how does it work internally", "tradeoffs", "when would you"
  Physics: "How does the double-slit experiment demonstrate wave-particle duality?"
  React: "How does React's reconciliation algorithm decide what to re-render?"

- Tier 3 (Practical): Give a concrete, hands-on scenario
  Physics: "Design an experiment to demonstrate conservation of momentum."
  React: "Your app leaks memory when navigating pages. How would you diagnose it?"

IMPORTANT:
- NEVER ask generic "Tell me about an underappreciated concept" questions
- NEVER ask teaching/soft-skill questions in Tier 1 or 2
- ALWAYS reference "{topic['topic']}" by name in the question
- Must be answerable by someone expert in {subject}
- Ask from a DIFFERENT ANGLE than previous sessions — vary the framing, scenario, or focus area each time

SESSION SEED: {random.randint(1000, 9999)} (use this to vary your question framing)

QUESTIONS ALREADY ASKED (never repeat):
{chr(10).join(f'- {q}' for q in asked_qs[-8:]) or 'None yet'}

Return JSON only:
{{"question": "short question referencing {topic['topic']}", "topic": "{topic['topic']}", "tier": "{tier.get('label', tier_key)}", "category": "{tier_key}", "difficulty": "easy|medium|hard", "type": "conceptual|applied|scenario", "what_to_evaluate": "key points a strong answer must cover"}}"""

    resolved_key = resolve_api_key(provider, api_key)
    text = await _call_chat_text_with_fallback(
        client, provider, resolved_key, model,
        system=STRUCTURED_Q_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=256,
        label=f"ladder-{tier_key}",
    )
    result = _parse_question_json(text, tier_key)
    result["category"] = tier_key  # ensure tier category is correct
    return result


async def _generate_project_question(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    blueprint: dict,
    session_state: dict,
) -> dict:
    """Generate a project deep-dive question from the resume."""
    import random
    projects = blueprint.get("notable_projects") or []
    asked_projects = session_state.get("askedProjects") or []
    asked_qs = session_state.get("questionsAsked") or []

    proj_lines = "\n".join(
        f"- {p.get('name', 'Unnamed')}: {p.get('description', '')} | Impact: {p.get('impact', 'N/A')}"
        for p in projects
    ) or "No specific projects listed — ask about general work experience."

    prompt = f"""CANDIDATE: {blueprint.get('candidate_name', 'Candidate')}
DOMAIN: {blueprint.get('primary_domain', 'General')}
SENIORITY: {blueprint.get('seniority_level', 'mid')}

PROJECTS AVAILABLE:
{proj_lines}

PROJECTS ALREADY ASKED ABOUT: {', '.join(asked_projects) or 'None yet'}

QUESTIONS ALREADY ASKED:
{chr(10).join(f'- {q}' for q in asked_qs[-8:]) or 'None yet'}

Ask about a SPECIFIC project from the resume. Focus on decisions, challenges, outcomes, and what they'd change. Do NOT repeat the same project.
Keep the question SHORT — 1-3 sentences, under 50 words. Ask ONE focused thing like a real interviewer would.
Vary the angle each session — sometimes ask about challenges, sometimes outcomes, sometimes architecture decisions.
SESSION SEED: {random.randint(1000, 9999)}

Return JSON only:
{{"question": "...", "topic": "...", "category": "project_based", "difficulty": "medium", "what_to_evaluate": "..."}}"""

    resolved_key = resolve_api_key(provider, api_key)
    text = await _call_chat_text_with_fallback(
        client, provider, resolved_key, model,
        system=STRUCTURED_Q_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=256,
        label="project-q",
    )
    return _parse_question_json(text, "project_based")


async def _generate_behavioral_question(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    blueprint: dict,
    session_state: dict,
) -> dict:
    """Generate a behavioral/STAR question tailored to seniority. For teachers, uses pedagogy_topics."""
    import random
    asked_qs = session_state.get("questionsAsked") or []
    themes = blueprint.get("behavioral_themes") or []
    pedagogy = blueprint.get("pedagogy_topics") or []
    role_type = blueprint.get("role_type") or "professional"

    # For educators, weave in pedagogy topics.
    pedagogy_hint = ""
    if pedagogy and role_type in ("teacher", "instructor", "professor"):
        pedagogy_hint = f"\nPEDAGOGY TOPICS TO WEAVE IN: {', '.join(pedagogy)}\nTry to ask about one of these pedagogy skills in a behavioral context.\n"

    prompt = f"""CANDIDATE: {blueprint.get('candidate_name', 'Candidate')}
DOMAIN: {blueprint.get('primary_domain', 'General')}
SUBJECT: {blueprint.get('subject_specialization') or blueprint.get('primary_domain', 'General')}
ROLE TYPE: {role_type}
SENIORITY: {blueprint.get('seniority_level', 'mid')}
EXPERIENCE: {blueprint.get('experience_years', 0)} years
BEHAVIORAL THEMES FROM RESUME: {', '.join(themes) or 'None detected'}
{pedagogy_hint}

QUESTIONS ALREADY ASKED:
{chr(10).join(f'- {q}' for q in asked_qs[-8:]) or 'None yet'}

Ask a situational/behavioral question using STAR format expectation.
Tailor to seniority: junior=learning/adapting, mid=collaboration/ownership,
senior=influence/mentoring, lead=team performance/strategy.
SESSION SEED: {random.randint(1000, 9999)} — vary the scenario each session.
Keep the question SHORT — 1-3 sentences, under 50 words. Ask ONE focused thing.

Return JSON only:
{{"question": "...", "topic": "...", "category": "behavioral", "difficulty": "medium", "what_to_evaluate": "..."}}"""

    resolved_key = resolve_api_key(provider, api_key)
    text = await _call_chat_text_with_fallback(
        client, provider, resolved_key, model,
        system=STRUCTURED_Q_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=256,
        label="behavioral-q",
    )
    return _parse_question_json(text, "behavioral")


async def _generate_resume_overview_question(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    blueprint: dict,
) -> dict:
    """Generate one light career overview question."""
    import random
    angles = [
        "Ask about the biggest career pivot or transition they've made and what drove it.",
        "Ask what has been the most defining project or role in shaping their current expertise.",
        "Ask how they ended up specialising in their domain — was it intentional or circumstantial?",
        "Ask what they're most proud of in their career so far and why.",
        "Ask what a typical challenge looks like in their day-to-day and how they approach it.",
        "Ask how their role or responsibilities have evolved over the years.",
        "Ask what motivated them to move into their current area of focus.",
    ]
    chosen_angle = random.choice(angles)
    prompt = f"""You are a senior interviewer conducting a warm-up question for a structured interview.
Ask ONE broad, conversational question based on this angle:

ANGLE: {chosen_angle}

Candidate context:
Domain: {blueprint.get('primary_domain', 'General')}
Seniority: {blueprint.get('seniority_level', 'mid')}
Career Summary: {blueprint.get('career_summary', 'Not provided')}

Keep the question SHORT (1-2 sentences), natural, and open-ended. Do not repeat a generic "tell me about yourself" question.

Return JSON only:
{{"question": "...", "topic": "career_overview", "category": "resume_overview", "difficulty": "easy", "what_to_evaluate": "..."}}"""

    resolved_key = resolve_api_key(provider, api_key)
    text = await _call_chat_text_with_fallback(
        client, provider, resolved_key, model,
        system=STRUCTURED_Q_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=256,
        label="overview-q",
    )
    return _parse_question_json(text, "resume_overview")


# ── Master question orchestrator ──

async def generate_structured_question(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    blueprint: dict,
    question_number: int,
    total_questions: int,
    session_state: dict,
    ladder: dict | None = None,
) -> dict:
    """Generate the next question using the progressive knowledge ladder."""

    if question_number < 1 or question_number > total_questions:
        return get_wrap_question()

    q_type, source = SESSION_FLOW[(question_number - 1) % len(SESSION_FLOW)]

    # Fixed questions.
    if source == "fixed":
        if q_type == "intro":
            return get_intro_question()
        if q_type == "resume_overview":
            return await _generate_resume_overview_question(client, provider, api_key, model, blueprint)
        if q_type == "wrap":
            return get_wrap_question()

    # Ladder questions (tier_1, tier_2, tier_3).
    if source == "ladder" and ladder:
        tier_counters = session_state.get("tierCounters") or {"tier_1": 0, "tier_2": 0, "tier_3": 0}
        topic_idx = tier_counters.get(q_type, 0)
        result = await _generate_ladder_question(
            client, provider, api_key, model,
            blueprint, ladder, q_type, topic_idx, session_state,
        )
        tier_counters[q_type] = topic_idx + 1
        session_state["tierCounters"] = tier_counters
        return result

    # Resume-based project question.
    if source == "resume":
        return await _generate_project_question(client, provider, api_key, model, blueprint, session_state)

    # Dynamic behavioral question.
    if source == "dynamic":
        return await _generate_behavioral_question(client, provider, api_key, model, blueprint, session_state)

    return get_wrap_question()


# ─── Blueprint + Ladder extraction (single call) ─────────

BLUEPRINT_SYSTEM = (
    "You are an expert technical recruiter, interviewer, and curriculum designer. "
    "You analyse resumes from ANY domain — software, teaching, healthcare, marketing, "
    "finance, law, design, etc. Return ONLY raw JSON — no markdown, no backticks."
)

# Domains / role titles that are too vague.
_VAGUE_DOMAINS = {
    "general", "general professional", "professional", "software",
    "software engineer", "software developer", "developer", "programmer",
    "specialist", "consultant", "expert", "it", "technology", "engineering",
    "education", "teaching", "educator", "trainer", "instructor",
    "healthcare", "legal", "finance", "science", "business", "management",
}

_VAGUE_TOPIC_KEYWORDS = {
    "concept", "skill", "knowledge", "understanding", "management",
    "planning", "communication", "general", "best practice", "underappreciated",
}


def _random_exclusion_hint(seed: int) -> str:
    """Generate a random instruction that forces the LLM to vary topic selection."""
    import random
    rng = random.Random(seed)
    strategies = [
        "Start your tier 1 list with the LEAST obvious foundational topic in this domain.",
        "Pick at least 2 topics that a typical interviewer would FORGET to ask about.",
        "Avoid the 5 most commonly Googled topics in this field — go deeper.",
        "Include at least 1 topic that would surprise the candidate.",
        "Focus tier 1 on practical fundamentals, not textbook definitions.",
        "For tier 2, pick topics that reveal real experience vs memorized answers.",
        "Include 1 cross-disciplinary topic that connects to an adjacent field.",
        "Pick topics that test understanding, not just recall.",
        "Start with a topic most candidates get wrong in interviews.",
        "For tier 3, pick a scenario the candidate likely faced but never prepared for.",
    ]
    picked = rng.sample(strategies, 3)
    return "\n".join(f"- {s}" for s in picked)


def build_blueprint_prompt(resume_text: str) -> str:
    import random
    seed = random.randint(10000, 99999)
    return f"""Analyse this resume carefully using MULTIPLE signals (job titles, skills,
projects, tools, education). Extract a precise interview blueprint with role detection
and a progressive knowledge ladder.

RESUME:
\"\"\"
{resume_text[:5000]}
\"\"\"

Return JSON only:
{{
  "candidate_name": "...",

  "primary_domain": "VERY SPECIFIC — e.g. React Frontend Development, Physics Education, Corporate Finance, iOS Mobile Development, Machine Learning Engineering. NEVER 'Software Engineer', 'Education', 'Healthcare', 'Developer'.",

  "subject_specialization": "Core subject — e.g. Physics, React.js, Tax Law, Oncology, JavaScript. For teachers this is their SUBJECT not 'teaching'.",

  "role_type": "frontend|backend|fullstack|devops|data_scientist|ml_engineer|data_analyst|mobile_ios|mobile_android|designer|teacher|doctor|finance_analyst|lawyer|hr_manager|marketing|sales|...",

  "primary_language_or_tool": "e.g. JavaScript, Python, Swift, Excel",
  "frameworks_and_stack": ["React", "Node.js", "PostgreSQL"],
  "experience_years": 0,
  "seniority_level": "junior|mid|senior|lead|manager",
  "is_technical": true,
  "core_skills": ["skill1", "skill2"],
  "tools_and_technologies": ["tool1"],

  "knowledge_ladder": {{
    "tier_1": {{
      "label": "Core Fundamentals",
      "focus": "Test SUBJECT knowledge — what every beginner must know",
      "topics": [
        "EXACT NAMED concept 1",
        "EXACT NAMED concept 2",
        "EXACT NAMED concept 3",
        "EXACT NAMED concept 4",
        "EXACT NAMED concept 5"
      ]
    }},
    "tier_2": {{
      "label": "Advanced Knowledge",
      "focus": "Deeper subject expertise — what separates good from great",
      "topics": [
        "EXACT NAMED concept 1",
        "EXACT NAMED concept 2",
        "EXACT NAMED concept 3",
        "EXACT NAMED concept 4",
        "EXACT NAMED concept 5"
      ]
    }},
    "tier_3": {{
      "label": "Applied & Practical",
      "focus": "Real-world application of subject knowledge",
      "topics": [
        "EXACT scenario topic 1",
        "EXACT scenario topic 2",
        "EXACT scenario topic 3",
        "EXACT scenario topic 4"
      ]
    }}
  }},

  "pedagogy_topics": [
    "ONLY for teachers/trainers — separated from subject knowledge",
    "e.g. Handling student misconceptions, Differentiated instruction",
    "Leave empty [] for non-educators"
  ],

  "notable_projects": [
    {{"name": "...", "description": "...", "tech_used": "...", "impact": "..."}}
  ],
  "career_summary": "2-3 sentence summary",
  "behavioral_themes": ["led a team", "handled deadlines"],

  "detection_reasoning": "2-3 sentences explaining which signals (job titles, projects, tools, skills, education) led to the domain and role_type conclusion"
}}

═══ ROLE DETECTION RULES ═══

Use ALL 5 signals — do NOT rely on job title alone:
  1. JOB TITLES across career — the PRIMARY pattern, not just the latest
  2. SKILLS — what's listed first / most frequently = primary
  3. PROJECTS — what they actually BUILT (strongest signal)
  4. TOOLS — heavy React/Vue/Angular = Frontend; Django/Spring/SQL = Backend; Docker/K8s = DevOps
  5. EDUCATION & CERTS — CS+React projects = Frontend; CPA = Finance; Education degree+subject = Teacher

DISAMBIGUATION:
  - If 70%+ work is UI/frontend → Frontend Developer (not Full Stack)
  - If 70%+ work is APIs/DB/server → Backend Developer (not Full Stack)
  - If genuinely mixed 40-60% → Full Stack Developer
  - "Rockstar Dev" / "Ninja Engineer" → normalise to actual role
  - "Software Engineer" title but all React projects → React Frontend Developer

═══ SUBJECT SPECIALIZATION (CRITICAL) ═══

For TEACHERS/EDUCATORS:
  - primary_domain MUST include the subject: "Physics Education" NOT "Education"
  - subject_specialization = the actual subject: "Physics" NOT "Teaching"
  - knowledge_ladder tiers 1-3 must test SUBJECT knowledge, NOT pedagogy
  - Pedagogy topics go in "pedagogy_topics" array ONLY

  Physics Teacher → tier 1: "Newton's Third Law", "Conservation of Momentum"
                    NOT: "classroom management", "lesson planning"

For DOCTORS: "Clinical Cardiology" NOT "Healthcare"
For LAWYERS: "Corporate Law" NOT "Legal"
For CHEFS:   "French Culinary Arts" NOT "Food Service"
For CAs:     "Chartered Accountancy" NOT "Finance"

═══ TOPIC NAMING RULES ═══

Every topic MUST be a specific NAMED concept that people Google:
  ✓ "Temporal Dead Zone"          ✗ "core JavaScript concept"
  ✓ "React reconciliation"       ✗ "React performance topic"
  ✓ "Newton's Third Law"         ✗ "physics fundamentals"
  ✓ "NPV vs IRR"                 ✗ "finance concept"
  ✓ "SOLID principles"           ✗ "general best practice"

TIER RULES:
  Tier 1 = things a junior must know (definitions, basics, "what is X")
  Tier 2 = mid/senior knowledge (internals, tradeoffs, "how/why does X work")
  Tier 3 = real-world scenarios (debugging, optimization, architecture)
  Topics come from DOMAIN KNOWLEDGE, not from the resume text.

EXAMPLES:
  React Dev tier 1: "var vs let vs const", "useState hook", "props vs state", "JSX syntax", "event handling in React"
  React Dev tier 2: "React reconciliation", "useCallback vs useMemo", "React Fiber", "code splitting", "virtual DOM diffing"
  React Dev tier 3: "Debugging memory leaks in React", "Optimising re-renders in large apps", "Infinite scroll with 100k items"
  Physics Teacher tier 1: "Newton's Laws of Motion", "Speed vs Velocity", "Ohm's Law", "Conservation of Energy", "Wave properties"
  Finance tier 1: "Balance sheet structure", "NPV vs IRR", "Time value of money", "WACC", "Ratio analysis"

seniority_level: 0-2 yrs=junior, 2-5=mid, 5-10=senior, 10+=lead/manager
is_technical: true for software/devops/data engineering; false for teaching/HR/marketing/sales

VARIATION RULE (CRITICAL):
Every domain has 30-50+ valid interview topics. You MUST pick different ones each session.
Do NOT default to the 5 most obvious topics — go broader.
SESSION SEED: {seed}

TOPIC SELECTION STRATEGY FOR THIS SESSION:
{_random_exclusion_hint(seed)}"""


def _validate_and_fix_blueprint(data: dict, resume_text: str) -> dict:
    """Validate blueprint quality and fix vague fields."""

    # ── Fix vague domain ──
    domain = str(data.get("primary_domain") or "").strip()
    subject = str(data.get("subject_specialization") or "").strip()
    role_type = str(data.get("role_type") or "").strip()

    if domain.lower() in _VAGUE_DOMAINS or not domain:
        # Try to derive from multiple signals.
        stack = data.get("frameworks_and_stack") or data.get("tools_and_technologies") or []
        lang = str(data.get("primary_language_or_tool") or "").strip()

        if role_type in ("teacher", "instructor", "professor") and subject:
            domain = f"{subject} Education"
        elif role_type == "teacher" and not subject:
            domain = "Education"  # can't do better without subject
        elif stack:
            domain = f"{lang} {stack[0]} Development".strip() if lang else f"{stack[0]} Development"
        elif lang:
            domain = f"{lang} Development"
        elif subject:
            domain = subject
        else:
            domain = "Software Development"
        _log(f"[blueprint] vague domain '{data.get('primary_domain')}' → '{domain}'")

    # ── Fix vague subject_specialization ──
    if not subject or subject.lower() in _VAGUE_DOMAINS:
        if role_type in ("teacher", "instructor", "professor"):
            # Try to extract subject from domain.
            for kw in ("Physics", "Chemistry", "Mathematics", "Math", "Biology",
                       "History", "English", "Computer Science", "Geography",
                       "Economics", "Accounting"):
                if kw.lower() in domain.lower() or kw.lower() in (data.get("career_summary") or "").lower():
                    subject = kw
                    break
        elif data.get("frameworks_and_stack"):
            subject = data["frameworks_and_stack"][0]
        elif data.get("primary_language_or_tool"):
            subject = str(data["primary_language_or_tool"]).strip()

    # ── Validate ladder topics are not vague ──
    raw_ladder = data.get("knowledge_ladder") or {}
    for tier_key in ("tier_1", "tier_2", "tier_3"):
        tier = raw_ladder.get(tier_key) or {}
        topics = tier.get("topics") or []
        vague_count = sum(
            1 for t in topics
            if any(kw in (t if isinstance(t, str) else str(t.get("topic", ""))).lower()
                   for kw in _VAGUE_TOPIC_KEYWORDS)
        )
        if vague_count > 1:
            _log(f"[blueprint] {tier_key} has {vague_count} vague topics — LLM quality issue")

    data["primary_domain"] = domain
    data["subject_specialization"] = subject
    return data


async def extract_interview_blueprint(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    resume_text: str,
) -> dict:
    """Extract a rich interview blueprint with embedded knowledge ladder."""
    resolved_key = resolve_api_key(provider, api_key)
    text = await _call_chat_text_with_fallback(
        client, provider, resolved_key, model,
        system=BLUEPRINT_SYSTEM,
        messages=[{"role": "user", "content": build_blueprint_prompt(resume_text)}],
        temperature=0.9,
        max_tokens=2048,
        label="blueprint",
    )
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ProviderResponseError(f"No JSON in blueprint response: {repr(text[:150])}")
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as error:
        raise ProviderResponseError(f"Could not parse blueprint JSON: {error.msg}") from error

    # Validate and fix vague fields.
    data = _validate_and_fix_blueprint(data, resume_text)
    domain = data["primary_domain"]

    # Parse embedded ladder.
    raw_ladder = data.get("knowledge_ladder") or {}
    ladder = {}
    for tier_key in ("tier_1", "tier_2", "tier_3"):
        tier = raw_ladder.get(tier_key) or {}
        topics_raw = tier.get("topics") or []
        topics = []
        for t in topics_raw[:5]:
            if isinstance(t, str) and t.strip():
                topics.append({
                    "topic": t.strip(),
                    "depth": "",
                    "sample_question_angle": "",
                })
            elif isinstance(t, dict) and t.get("topic"):
                topics.append({
                    "topic": str(t["topic"]).strip(),
                    "depth": str(t.get("depth", "")).strip(),
                    "sample_question_angle": str(t.get("sample_question_angle", "")).strip(),
                })
        label_defaults = {"tier_1": "Foundations", "tier_2": "Advanced Concepts", "tier_3": "Real-World Problem Solving"}
        level_defaults = {"tier_1": "foundational", "tier_2": "advanced", "tier_3": "expert_practical"}
        ladder[tier_key] = {
            "level": level_defaults.get(tier_key, tier_key),
            "label": str(tier.get("label") or label_defaults.get(tier_key, tier_key)).strip(),
            "description": str(tier.get("description", "")).strip(),
            "focus": str(tier.get("focus", "")).strip(),
            "topics": topics,
        }

    subject = str(data.get("subject_specialization") or "").strip()
    role_type = str(data.get("role_type") or "").strip()

    _log(
        f"[blueprint] domain={domain}, subject={subject}, role_type={role_type}, "
        f"seniority={data.get('seniority_level')}, years={data.get('experience_years')}, "
        f"t1={[t['topic'] for t in ladder['tier_1']['topics']]}, "
        f"t2={[t['topic'] for t in ladder['tier_2']['topics']]}, "
        f"t3={[t['topic'] for t in ladder['tier_3']['topics']]}",
        file=sys.stderr,
    )

    return {
        "candidate_name": str(data.get("candidate_name") or "Candidate").strip(),
        "primary_domain": domain,
        "subject_specialization": subject,
        "role_type": role_type,
        "primary_language_or_tool": str(data.get("primary_language_or_tool") or "").strip(),
        "frameworks_and_stack": [str(s).strip() for s in (data.get("frameworks_and_stack") or []) if str(s).strip()][:8],
        "experience_years": int(data.get("experience_years") or 0),
        "seniority_level": str(data.get("seniority_level") or "mid").strip(),
        "is_technical": bool(data.get("is_technical", True)),
        "core_skills": [str(s).strip() for s in (data.get("core_skills") or []) if str(s).strip()][:10],
        "tools_and_technologies": [str(t).strip() for t in (data.get("tools_and_technologies") or []) if str(t).strip()][:10],
        "domain_core_concepts": [str(c).strip() for c in (data.get("domain_core_concepts") or []) if str(c).strip()][:12],
        "knowledge_ladder": ladder,
        "pedagogy_topics": [str(p).strip() for p in (data.get("pedagogy_topics") or []) if str(p).strip()][:6],
        "notable_projects": (data.get("notable_projects") or [])[:5],
        "career_summary": str(data.get("career_summary") or "").strip(),
        "behavioral_themes": [str(b).strip() for b in (data.get("behavioral_themes") or []) if str(b).strip()][:6],
        "detection_reasoning": str(data.get("detection_reasoning") or "").strip(),
    }


# ─── Session report generation ────────────────────────────

SESSION_REPORT_SYSTEM = (
    "You generate comprehensive mock interview performance reports. "
    "Return ONLY raw JSON — no markdown, no backticks, no commentary."
)


def build_session_report_prompt(blueprint: dict, answers: list[dict]) -> str:
    transcript = "\n\n".join(
        f"Q{i+1} [{a.get('category', 'unknown')}]: {a.get('question', '')}\n"
        f"Answer: {a.get('answer', '')}\n"
        f"Score: {a.get('score', 'N/A')}/100"
        for i, a in enumerate(answers)
    )
    scores_summary = "\n".join(
        f"- Q{i+1}: {a.get('score', 'N/A')}/100 | {a.get('category', '')} | {a.get('feedback', '')}"
        for i, a in enumerate(answers)
    )
    return f"""CANDIDATE: {blueprint.get('candidate_name', 'Candidate')}
DOMAIN: {blueprint.get('primary_domain', 'General')}
SENIORITY: {blueprint.get('seniority_level', 'mid')}
EXPERIENCE: {blueprint.get('experience_years', 0)} years

INTERVIEW TRANSCRIPT:
{transcript}

INDIVIDUAL SCORES:
{scores_summary}

Generate a performance report. Return JSON only:
{{
  "overall_score": 0-100,
  "grade": "A+|A|B+|B|C+|C|D|F",
  "hire_recommendation": "Strong Hire|Hire|Maybe|No Hire",
  "summary": "3-4 sentence executive summary",
  "category_scores": {{
    "domain_knowledge": {{"score": 0-10, "feedback": "..."}},
    "technical_skills": {{"score": 0-10, "feedback": "..."}},
    "project_experience": {{"score": 0-10, "feedback": "..."}},
    "communication": {{"score": 0-10, "feedback": "..."}},
    "behavioral": {{"score": 0-10, "feedback": "..."}}
  }},
  "strengths": ["strength1", "strength2", "strength3"],
  "improvement_areas": ["area1", "area2", "area3"],
  "question_breakdown": [
    {{"question_number": 1, "category": "...", "score": 0-100, "one_line_feedback": "..."}}
  ],
  "next_steps": ["step1", "step2", "step3"]
}}"""


async def generate_session_report(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    blueprint: dict,
    answers: list[dict],
) -> dict:
    """Generate a comprehensive end-of-session interview report."""
    resolved_key = resolve_api_key(provider, api_key)
    text = await _call_chat_text_with_fallback(
        client, provider, resolved_key, model,
        system=SESSION_REPORT_SYSTEM,
        messages=[{"role": "user", "content": build_session_report_prompt(blueprint, answers)}],
        temperature=0.2,
        max_tokens=2048,
        label="report",
    )
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ProviderResponseError(f"No JSON in report: {repr(text[:150])}")
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as error:
        raise ProviderResponseError(f"Could not parse report JSON: {error.msg}") from error


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
1. SEMANTIC INTERPRETATION: Correct obvious voice transcription errors mentally, then evaluate meaning.
2. CONCEPT EXTRACTION: Identify 3–5 key things this question requires; note what the answer showed for a {level} {role}.
3. SCORING RUBRIC (apply leniency above):
   - 85-100 (correct): Covers key points accurately for a {level} {role}
   - 50-84 (partial): Clear understanding of some points, misses others
   - 20-49 (partial): Awareness with significant gaps
   - 0-19 (incorrect): No meaningful understanding or irrelevant/blank
4. VERDICT: "correct" if score >= 75; "partial" if score >= 30; "incorrect" if score < 30

FEEDBACK VOICE (senior peer — concise coaching card, {domain} terminology):
- strength: ONE line, max 6 words, genuine signal only in {domain} terms. Use "" if nothing real — forbid "Attempted", "Tried", "Managed to".
- gaps: JSON array of 0–2 strings. Each max 8 words — neutral gap, not blame. Use [] if nothing material.
- missing: Same gaps joined with " · ".
- hint: Coaching redirect, max 12 words — NOT a question. Do NOT start with "You should", "You need to", "You must". Use "" if nothing to add.
- ideal: Max 3 sentences, first person, as a strong {role} would say it.

Respond with ONLY a raw JSON object — no markdown, no backticks, no explanation outside the JSON:
{{"score": <integer 0-100>, "verdict": "correct"|"partial"|"incorrect", "strength": "<string>", "gaps": ["<optional>", "<optional>"], "missing": "<string>", "hint": "<string>", "ideal": "<string>"}}"""


# ─── Transcript cleanup ───────────────────────────────────

TRANSCRIPT_CLEANUP_SYSTEM = (
    "You clean up raw speech-to-text transcripts from mock interviews. "
    "Return ONLY the corrected transcript — no extra commentary, no quotes, no labels."
)


def build_transcript_cleanup_prompt(raw: str) -> str:
    return f"""The following is a raw speech-to-text transcript from a mock interview.

Fix ONLY:
- Obvious speech recognition errors (homophones, broken words, e.g. "letten const" → "let and const", "temporal dead son" → "temporal dead zone")
- Missing or wrong punctuation
- Run-on fragments from interim captures

Do NOT:
- Change the meaning or intent
- Add content the candidate didn't say
- Rephrase or improve the answer
- Remove filler words like "um", "uh" (the evaluator expects natural speech)

Raw transcript:
\"\"\"
{raw}
\"\"\"

Return ONLY the corrected transcript, nothing else."""


async def clean_transcript(
    client: httpx.AsyncClient,
    provider: str,
    api_key: str,
    model: str,
    raw_transcript: str,
) -> str:
    """Clean up a raw speech-to-text transcript using a lightweight LLM call."""
    if len(raw_transcript.strip()) < 15:
        return raw_transcript  # too short to be worth cleaning

    resolved_key = resolve_api_key(provider, api_key)
    try:
        text = await _call_chat_text_with_fallback(
            client, provider, resolved_key, model,
            system=TRANSCRIPT_CLEANUP_SYSTEM,
            messages=[{"role": "user", "content": build_transcript_cleanup_prompt(raw_transcript)}],
            temperature=0.1,
            max_tokens=1024,
            label="cleanup",
        )
        cleaned = text.strip().strip('"').strip("'").strip()
        return cleaned if cleaned else raw_transcript
    except Exception as error:
        _log(f"[cleanup] transcript cleanup failed (non-fatal): {error}", file=sys.stderr)
        return raw_transcript


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
