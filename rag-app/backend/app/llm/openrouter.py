"""Thin OpenRouter wrapper used by adapters."""
from __future__ import annotations

from typing import Any, Dict, List

from backend.app.llm.clients.openrouter import (
    OpenRouterAuthError,
    OpenRouterHTTPError,
    chat_sync,
)


def chat(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.0,
    top_p: float | None = None,
    max_tokens: int | None = None,
    extra: Dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> Dict[str, Any]:
    """Synchronous chat call to OpenRouter /chat/completions."""

    return chat_sync(
        model=model,
        messages=messages,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        extra=extra,
        timeout=timeout,
    )


__all__ = ["chat", "OpenRouterAuthError", "OpenRouterHTTPError"]
