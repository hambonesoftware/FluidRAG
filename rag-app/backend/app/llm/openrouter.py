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
    timeout: float | None = None,
) -> dict[str, Any]:
    """Synchronous chat call to OpenRouter /chat/completions."""
    try:
        from ..config import get_settings

        settings = get_settings()
        effective_timeout = (
            timeout if timeout is not None else settings.openrouter_timeout_seconds
        )
        retries = settings.openrouter_max_retries
        return chat_sync(
            model=model,
            messages=messages,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            extra=extra,
            timeout=effective_timeout,
            retries=retries,
        )
    except ClientAuthError as exc:  # pragma: no cover - pass-through mapping
        raise OpenRouterAuthError(str(exc)) from exc
    except ClientHTTPError as exc:
        raise OpenRouterHTTPError(str(exc)) from exc


__all__ = ["OpenRouterAuthError", "OpenRouterHTTPError", "chat"]
