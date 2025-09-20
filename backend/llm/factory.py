from __future__ import annotations
import os
from typing import Optional

from .clients.openrouter import OpenRouterClient
from .clients.llamacpp import LlamaCppClient
from .clients.base import BaseLLMClient

def create_llm_client(provider: str | None) -> BaseLLMClient:
    normalized = (provider or "openrouter").strip().lower()
    if normalized == "llamacpp":
        return LlamaCppClient()
    return OpenRouterClient()

def provider_default_model(provider: str | None) -> Optional[str]:
    normalized = (provider or "openrouter").strip().lower()
    if normalized == "llamacpp":
        return os.environ.get("LLAMACPP_DEFAULT_MODEL")
    return os.environ.get("OPENROUTER_DEFAULT_MODEL")
