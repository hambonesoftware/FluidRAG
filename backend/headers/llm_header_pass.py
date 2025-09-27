from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Dict, List

from backend.llm.factory import create_llm_client, provider_default_model
from backend.models.headers import HeaderCandidate, Judging

LOGGER = logging.getLogger(__name__)

LLM_PROMPT = "Please list all header sections of this document and provide the results in a json format"


def call_llm(raw_text: str) -> str:
    """Invoke the project LLM client and return the raw string response."""

    provider = os.environ.get("HEADER_LLM_PROVIDER")
    model = (
        os.environ.get("HEADER_LLM_MODEL")
        or provider_default_model(provider)
        or os.environ.get("OPENROUTER_DEFAULT_MODEL")
        or "openai/gpt-4o-mini"
    )

    client = create_llm_client(provider)

    user_prompt = LLM_PROMPT
    raw_text = raw_text.strip()
    if raw_text:
        user_prompt = f"{LLM_PROMPT}\n\n{raw_text}"

    loop = asyncio.new_event_loop()
    try:
        previous_loop = asyncio.get_event_loop()
    except Exception:
        previous_loop = None
    try:
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            client.acomplete(
                model=model,
                system=None,
                user=user_prompt,
                temperature=0.0,
                max_tokens=2048,
                stream=False,
            )
        )
    finally:
        try:
            loop.close()
        finally:
            # Restore previous loop if possible
            try:
                if previous_loop is not None:
                    asyncio.set_event_loop(previous_loop)
                else:
                    asyncio.set_event_loop(None)  # type: ignore[arg-type]
            except Exception:
                pass

    return result if isinstance(result, str) else str(result)


def parse_llm_json(raw_response: str) -> List[Dict[str, Any]]:
    """Parse the LLM response into a list of header descriptor dictionaries."""

    obj = json.loads(raw_response)
    if isinstance(obj, dict):
        for key in ("headers", "sections", "results", "items"):
            value = obj.get(key)
            if isinstance(value, list):
                return value
        raise ValueError("No list found in LLM JSON object.")
    if isinstance(obj, list):
        return obj
    raise ValueError("Unexpected LLM JSON structure.")


def coerce_llm_candidates(llm_items: List[Dict[str, Any]]) -> List[HeaderCandidate]:
    """Convert generic LLM JSON entries into :class:`HeaderCandidate` objects."""

    candidates: List[HeaderCandidate] = []
    for item in llm_items:
        if not isinstance(item, dict):
            continue
        section_id = item.get("section_id") or item.get("id") or item.get("number")
        title = (item.get("title") or item.get("name") or "").strip()
        if not title:
            continue

        level_raw = item.get("level")
        try:
            level = int(level_raw) if level_raw is not None else None
        except Exception:
            level = None

        page_raw = item.get("page")
        try:
            page = int(page_raw) if page_raw is not None else None
        except Exception:
            page = None

        span_raw = item.get("span_char") or item.get("span") or item.get("char_span")
        span_char = None
        if isinstance(span_raw, (list, tuple)) and len(span_raw) == 2:
            span_char = (span_raw[0], span_raw[1])  # type: ignore[arg-type]
        elif isinstance(span_raw, dict):
            start = span_raw.get("start") or span_raw.get("begin")
            end = span_raw.get("end") or span_raw.get("stop")
            if start is not None and end is not None:
                span_char = (start, end)  # type: ignore[arg-type]

        confidence_raw = item.get("confidence")
        llm_conf = None
        if isinstance(confidence_raw, (int, float)):
            llm_conf = float(confidence_raw)

        extra_fields: Dict[str, str] = {}
        for key, value in item.items():
            if key in {
                "title",
                "name",
                "level",
                "page",
                "span_char",
                "span",
                "char_span",
                "id",
                "number",
                "section_id",
                "confidence",
            }:
                continue
            extra_fields[key] = str(value)

        judging = Judging(
            llm_confidence=llm_conf,
            llm_raw_fields=extra_fields,
            page=page,
            span_char=span_char,
        )

        candidates.append(
            HeaderCandidate(
                source="llm",
                section_id=str(section_id) if section_id is not None else None,
                title=title,
                level=level,
                page=page,
                span_char=span_char,
                judging=judging,
            )
        )
    return candidates


def run_llm_header_pass(full_normalized_text: str) -> Dict[str, Any]:
    """Execute the LLM header pass and return raw output + coerced candidates."""

    raw_response = ""
    parse_error: str | None = None
    candidates: List[HeaderCandidate] = []

    try:
        raw_response = call_llm(full_normalized_text)
        if raw_response:
            items = parse_llm_json(raw_response)
            candidates = coerce_llm_candidates(items)
    except Exception as exc:  # pragma: no cover - defensive logging path
        parse_error = str(exc)
        LOGGER.warning("LLM header pass failed: %s", exc)

    return {
        "raw_response": raw_response,
        "parse_error": parse_error,
        "candidates": candidates,
    }


__all__ = [
    "LLM_PROMPT",
    "call_llm",
    "coerce_llm_candidates",
    "parse_llm_json",
    "run_llm_header_pass",
]
