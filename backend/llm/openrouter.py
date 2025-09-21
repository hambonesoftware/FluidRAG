from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

import httpx

from ..utils.envsafe import openrouter_headers
from .utils import OPENROUTER_URL

log = logging.getLogger("FluidRAG.llm.openrouter_call")


def call_chat_completions(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke OpenRouter's chat completions endpoint synchronously with detailed logging."""

    headers = openrouter_headers()
    safe_headers = {
        key: ("***" if key.lower() == "authorization" and value else value)
        for key, value in headers.items()
    }
    body_len = len(json.dumps(payload, ensure_ascii=False))
    log.info("LLM → POST %s body_bytes=%d model=%r", OPENROUTER_URL, body_len, payload.get("model"))
    log.debug("LLM headers (masked): %s", safe_headers)

    start = time.perf_counter()
    with httpx.Client(timeout=httpx.Timeout(60.0)) as client:
        response = client.post(OPENROUTER_URL, headers=headers, json=payload)
        elapsed = time.perf_counter() - start
        log.info(
            "LLM ← %s in %.2fs, body_bytes=%d",
            response.status_code,
            elapsed,
            len(response.content),
        )
        response.raise_for_status()
        return response.json()
