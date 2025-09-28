"""Environment helpers for OpenRouter integration."""

from __future__ import annotations

import os


def mask_bearer(token: str | None) -> str:
    """Mask a bearer token for log output."""
    if not token:
        return ""
    raw = token.strip()
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]}"


def openrouter_headers() -> dict[str, str]:
    """Build OpenRouter headers from environment variables."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for OpenRouter calls.")

    referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
    title = os.getenv("OPENROUTER_APP_TITLE", "FluidRAG").strip()

    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return headers


def masked_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of ``headers`` with Authorization masked."""
    sanitized = dict(headers)
    auth_header = sanitized.get("Authorization")
    if auth_header:
        scheme, token = (auth_header.split(" ", 1) + [""])[:2]
        masked = mask_bearer(token) if token else mask_bearer(auth_header)
        if token:
            sanitized["Authorization"] = f"{scheme} {masked}".strip()
        else:
            sanitized["Authorization"] = masked
    return sanitized


__all__ = ["mask_bearer", "openrouter_headers", "masked_headers"]
