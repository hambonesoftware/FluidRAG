"""Thin wrapper around OpenRouter client for synchronous usage."""

from __future__ import annotations

from typing import Any

from .clients.openrouter import (
    OpenRouterAuthError as ClientAuthError,
)
from .clients.openrouter import (
    OpenRouterHTTPError as ClientHTTPError,
)
from .clients.openrouter import (
    chat_sync,
)


class OpenRouterAuthError(Exception):
    """Auth error (401)."""


class OpenRouterHTTPError(Exception):
    """HTTP/transport error."""


def chat(
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.0,
    top_p: float | None = None,
    max_tokens: int | None = None,
    extra: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Synchronous chat call to OpenRouter /chat/completions."""
    try:
        return chat_sync(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            extra=extra,
            timeout=timeout,
        )
    except ClientAuthError as exc:  # pragma: no cover - pass-through mapping
        raise OpenRouterAuthError(str(exc)) from exc
    except ClientHTTPError as exc:
        raise OpenRouterHTTPError(str(exc)) from exc


__all__ = ["OpenRouterAuthError", "OpenRouterHTTPError", "chat"]
