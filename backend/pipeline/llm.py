# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import httpx
from typing import Any, Dict, List, Optional

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
DEFAULT_PROVIDER   = os.getenv("LLM_PROVIDER", "openrouter")
DEFAULT_MODEL      = os.getenv("HEADER_MODEL", "x-ai/grok-4-fast:free")

class ORClient:
    """Minimal async client for OpenRouter's chat completions."""
    def __init__(self, model: str):
        self.model = model
        self.base  = "https://openrouter.ai/api/v1"

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.0, max_tokens: int = 512) -> Dict[str, Any]:
        if not OPENROUTER_API_KEY:
            # No key available; pretend success with empty result
            return {"text": "ok"}
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{self.base}/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"text": text}

class LlamaCppClient:
    """Placeholder client for a local llama.cpp server, if you wire one up later."""
    def __init__(self, model: str, endpoint: Optional[str] = None):
        self.model = model
        self.endpoint = endpoint or os.getenv("LLAMACPP_ENDPOINT", "http://127.0.0.1:8080")

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.0, max_tokens: int = 512) -> Dict[str, Any]:
        # Basic completion-style bridge; adapt if your server uses a different schema.
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{self.endpoint}/v1/chat/completions", json=payload)
            r.raise_for_status()
            data = r.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"text": text}

def _make_client(provider: str, model: str):
    provider = (provider or DEFAULT_PROVIDER).strip().lower()
    model    = (model or DEFAULT_MODEL).strip()
    if provider in ("openrouter", "openrouter.ai", "or"):
        return ORClient(model=model)
    if provider in ("llamacpp", "llama.cpp", "llmcpp"):
        return LlamaCppClient(model=model)
    # default fallback
    return ORClient(model=model)

def create_llm_client(*args, **kwargs):
    """
    Flexible factory:
      - create_llm_client(provider, model)
      - create_llm_client(model="...", provider="...")
      - create_llm_client()  -> uses env defaults
    """
    provider = None
    model = None
    if len(args) == 2:
        provider, model = args[0], args[1]
    elif len(args) == 1:
        # If you ever had a positional single-arg version, treat it as model
        model = args[0]
    provider = kwargs.get("provider", provider)
    model    = kwargs.get("model", model)
    provider = provider or DEFAULT_PROVIDER
    model    = model or DEFAULT_MODEL
    return _make_client(provider, model)

# Back-compat alias
get_llm_client = create_llm_client
