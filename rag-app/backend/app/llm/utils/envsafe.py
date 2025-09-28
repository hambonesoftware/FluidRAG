"""Environment safe helpers for OpenRouter headers."""
from __future__ import annotations

from typing import Dict


def mask_bearer(token: str | None) -> str:
    if not token:
        return "<missing>"
    if len(token) <= 6:
        return "***"
    return f"{token[:3]}...{token[-2:]}"


def openrouter_headers(api_key: str | None) -> Dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def masked_headers(api_key: str | None) -> Dict[str, str]:
    headers = openrouter_headers(api_key)
    if "Authorization" in headers:
        headers["Authorization"] = mask_bearer(api_key)
    return headers
