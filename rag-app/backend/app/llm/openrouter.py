"""Thin sync wrapper for OpenRouter chat."""
from __future__ import annotations

from typing import Any, Dict, List

from ..config import settings
from ..util.logging import get_logger
from .clients import openrouter as client

logger = get_logger(__name__)


class OpenRouterAuthError(RuntimeError):
    pass


class OpenRouterHTTPError(RuntimeError):
    pass


def chat(*, model: str, messages: List[Dict[str, str]], **kwargs: Any) -> Dict[str, Any]:
    if not settings.openrouter_api_key:
        raise OpenRouterAuthError("OPENROUTER_API_KEY missing")
    try:
        return client.chat_sync(model=model, messages=messages, **kwargs)
    except client.OpenRouterAuthError as exc:  # type: ignore[attr-defined]
        raise OpenRouterAuthError(str(exc)) from exc
    except client.OpenRouterHTTPError as exc:  # type: ignore[attr-defined]
        raise OpenRouterHTTPError(str(exc)) from exc
