"""LLM utility helpers."""
from __future__ import annotations

import json
from typing import Any, Dict, List

from backend.app.config import settings
from backend.app.util.logging import get_logger

logger = get_logger(__name__, settings.log_level)


def windows_curl(url: str) -> str:
    return f"powershell -Command \"Invoke-WebRequest -Uri '{url}'\""


def log_prompt(messages: List[Dict[str, Any]]) -> None:
    try:
        pretty = json.dumps(messages, indent=2)
    except (TypeError, ValueError):
        pretty = str(messages)
    logger.debug("LLM prompt", extra={"messages": pretty})
