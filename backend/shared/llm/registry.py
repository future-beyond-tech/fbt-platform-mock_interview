"""
shared/llm/registry.py — Provider registry and factory.

A single place that owns all adapter instances.  Call ``get_provider(name)``
to retrieve the adapter for a given provider id.  Adapters are singletons —
one instance per process, shared across all requests.
"""

from __future__ import annotations

from config import settings
from shared.llm.ports import LLMProvider
from shared.llm.adapters.ollama import OllamaAdapter
from shared.llm.adapters.gemini import GeminiAdapter
from shared.llm.adapters.groq import GroqAdapter
from shared.llm.adapters.openai import OpenAIAdapter
from shared.llm.adapters.anthropic import AnthropicAdapter

# ── Registry ─────────────────────────────────────────────────────────────────
# Keys must match the provider id strings used everywhere in the codebase.
_REGISTRY: dict[str, LLMProvider] = {
    "ollama": OllamaAdapter(base_url=settings.ollama_base_url),
    "gemini": GeminiAdapter(api_key=settings.gemini_api_key),
    "groq": GroqAdapter(api_key=settings.groq_api_key),
    "openai": OpenAIAdapter(api_key=settings.openai_api_key),
    "anthropic": AnthropicAdapter(api_key=settings.anthropic_api_key),
}


def get_provider(name: str) -> LLMProvider:
    """Return the adapter for *name*.

    Raises:
        ValueError: If *name* is not in the registry.
    """
    if name not in _REGISTRY:
        raise ValueError(f"Unknown LLM provider: {name!r}. Available: {list_providers()}")
    return _REGISTRY[name]


def list_providers() -> list[str]:
    """Return all registered provider ids."""
    return list(_REGISTRY.keys())
