"""Utility helpers for OpenRouter interactions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__path__ = [str(Path(__file__).with_name("utils"))]
if __spec__ is not None:  # pragma: no cover - package wiring
    __spec__.submodule_search_locations = __path__
    __package__ = __spec__.parent  # type: ignore[assignment]

from .envsafe import masked_headers


def windows_curl(url: str, headers: dict[str, str], payload: dict[str, Any]) -> str:
    """Build a Windows-friendly ``curl`` command for debugging."""
    escaped_headers = " ^\n  ".join(
        f'-H "{_escape_quotes(key)}: {_escape_quotes(value)}"'
        for key, value in headers.items()
    )
    body = _escape_quotes(json.dumps(payload, ensure_ascii=False))
    parts = [f'curl -X POST "{_escape_quotes(url)}"']
    if escaped_headers:
        parts.append(escaped_headers)
    parts.append(f'-d "{body}"')
    return " ^\n  ".join(parts)


def log_prompt(
    prefix: str, payload: dict[str, Any], hdrs: dict[str, str]
) -> dict[str, Any]:
    """Return compact metadata describing a prompt for logging."""
    messages = payload.get("messages", []) or []
    last = messages[-1] if messages else {}
    preview = last.get("content", "")
    if preview and len(preview) > 120:
        preview = f"{preview[:117]}..."
    meta = {
        "stage": prefix,
        "model": payload.get("model"),
        "temperature": payload.get("temperature"),
        "messages": len(messages),
        "headers": masked_headers(hdrs),
    }
    if preview:
        meta["last"] = preview
    if payload.get("max_tokens") is not None:
        meta["max_tokens"] = payload["max_tokens"]
    if payload.get("top_p") is not None:
        meta["top_p"] = payload["top_p"]
    if payload.get("extra"):
        meta["has_extra"] = True
    return meta


def _escape_quotes(value: str) -> str:
    return value.replace('"', '\\"')


__all__ = ["windows_curl", "log_prompt"]
