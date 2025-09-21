from __future__ import annotations

import os
from typing import Any, Dict

DEFAULT_REFERER = "http://localhost:5142"
DEFAULT_TITLE = "FluidRAG"


def s(value: Any, default: str = "") -> str:
    """Return a stripped string when ``value`` is a string; otherwise the default."""

    if isinstance(value, str):
        return value.strip()
    return default


def env(name: str, default: str = "") -> str:
    """Fetch an environment variable safely, returning ``default`` when unset/non-string."""

    value = os.environ.get(name)
    if isinstance(value, str):
        return value.strip()
    return default


def openrouter_headers() -> Dict[str, str]:
    """Build OpenRouter headers without raising if optional metadata is missing."""

    api_key = env("OPENROUTER_API_KEY")
    referer = env("OPENROUTER_HTTP_REFERER") or env("OPENROUTER_SITE_URL") or DEFAULT_REFERER
    title = env("OPENROUTER_APP_TITLE", DEFAULT_TITLE)
    headers: Dict[str, str] = {
        "Authorization": f"Bearer {api_key}" if api_key else "",
        "HTTP-Referer": referer,
        "X-Title": title,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    return headers
