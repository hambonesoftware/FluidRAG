from __future__ import annotations

import os
from typing import Any, Dict
from urllib.parse import urlparse, urlunparse

from .strings import s

DEFAULT_REFERER = "http://localhost:5142"
DEFAULT_TITLE = "FluidRAG"


def env(name: str, default: str = "") -> str:
    """Fetch an environment variable safely, returning ``default`` when unset/non-string."""

    value: Any = os.environ.get(name)
    if isinstance(value, str):
        return value.strip()
    return default


def _ensure_origin(candidate: str) -> str:
    """Normalize ``candidate`` to an origin (scheme://host[:port]) or ``""``."""

    value = s(candidate)
    if not value:
        return ""

    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))

    # Allow bare host[:port] – assume http.
    if parsed.path and not parsed.scheme and not parsed.netloc:
        host = parsed.path.strip()
        if host:
            return f"http://{host}"

    return ""


def get_app_origin() -> str:
    """Resolve the application origin used for Referer headers and logging."""

    candidates = (
        env("APP_ORIGIN"),
        env("FRONTEND_ORIGIN"),
        env("OPENROUTER_HTTP_REFERER"),
        env("OPENROUTER_SITE_URL"),
    )

    for candidate in candidates:
        origin = _ensure_origin(candidate)
        if origin and "openrouter.ai" not in origin.lower():
            return origin

    return DEFAULT_REFERER


def openrouter_headers() -> Dict[str, str]:
    """Build OpenRouter headers without raising if optional metadata is missing."""

    api_key = s(env("OPENROUTER_API_KEY"))
    title = env("OPENROUTER_APP_TITLE", DEFAULT_TITLE)
    headers: Dict[str, str] = {
        "HTTP-Referer": get_app_origin(),
        "X-Title": title,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers
