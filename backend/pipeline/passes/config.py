"""Configuration helpers for pass execution."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Union


from backend.prompts import PASS_PROMPTS
from backend.utils.envsafe import env
from backend.utils.strings import s

from .constants import (
    DEFAULT_PASS_BACKOFF_FACTOR,
    DEFAULT_PASS_BACKOFF_INITIAL_MS,
    DEFAULT_PASS_BACKOFF_MAX_MS,
    DEFAULT_PASS_CONCURRENCY,
    DEFAULT_PASS_MAX_ATTEMPTS,
    DEFAULT_PASS_MAX_TOKENS,
    DEFAULT_PASS_TEMPERATURE,
    DEFAULT_PASS_TIMEOUT_S,
    PASS_FLAG_TO_NAME,
)


def canonical_pass_name(raw: Any) -> Optional[str]:
    """Return the canonical pass name if recognised."""

    candidate = s(raw)
    if not candidate:
        return None

    normalized = " ".join(candidate.replace("_", " ").replace("-", " ").split()).lower()
    if normalized in {"", "none"}:
        return None

    for canonical in PASS_PROMPTS:
        if normalized == canonical.lower():
            return canonical

    alias_map = {
        "mech": "Mechanical",
        "mechanical": "Mechanical",
        "electrical": "Electrical",
        "controls": "Controls",
        "control": "Controls",
        "software": "Software",
        "pm": "Project Management",
        "project management": "Project Management",
        "project_management": "Project Management",
        "projectmanagement": "Project Management",
    }

    return alias_map.get(normalized)


def is_truthy_flag(value: Any) -> bool:
    """Interpret user-supplied boolean-like flags."""

    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no", "off", "none", "null"}:
            return False
        return True
    return bool(value)


def resolve_pass_items(payload: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Determine which passes should be executed for the request."""

    requested: List[str] = []
    unknown: List[str] = []

    passes_field = payload.get("passes")
    if isinstance(passes_field, dict):
        sources = [name for name, enabled in passes_field.items() if enabled]
    elif isinstance(passes_field, (list, tuple, set)):
        sources = list(passes_field)
    elif isinstance(passes_field, str):
        sources = [passes_field]
    else:
        sources = []

    for source in sources:
        canonical = canonical_pass_name(source)
        if canonical:
            requested.append(canonical)
        else:
            text = s(source)
            if text:
                unknown.append(text)

    if not requested:
        for flag, canonical in PASS_FLAG_TO_NAME.items():
            try:
                enabled = payload.get(flag)
            except AttributeError:
                enabled = None
            if is_truthy_flag(enabled):
                requested.append(canonical)

    if not requested:
        names = list(PASS_PROMPTS.keys())
    else:
        seen = set()
        names = []
        for name in requested:
            if name in PASS_PROMPTS and name not in seen:
                names.append(name)
                seen.add(name)
            elif name not in PASS_PROMPTS:
                unknown.append(name)

    items = [(name, PASS_PROMPTS[name]) for name in names if name in PASS_PROMPTS]
    return items, unknown


def _int_from_env(name: str, default: int) -> int:
    try:
        value = int(env(name))
    except (TypeError, ValueError):
        return default
    return value


def _float_from_env(name: str, default: float) -> float:
    try:
        value = float(env(name))
    except (TypeError, ValueError):
        return default
    return value


def resolve_pass_concurrency(payload: Dict[str, Any]) -> int:
    """Resolve how many passes should execute concurrently."""

    source = (
        payload.get("max_parallel_passes")
        or payload.get("pass_concurrency")
        or env("LLM_PASS_CONCURRENCY")
        or DEFAULT_PASS_CONCURRENCY
    )
    try:
        value = int(source)
    except (TypeError, ValueError):
        return DEFAULT_PASS_CONCURRENCY
    return max(1, value)


def resolve_pass_timeout(payload: Dict[str, Any]) -> float:
    """Resolve the timeout for individual pass requests."""

    source = (
        payload.get("pass_timeout_seconds")
        or env("LLM_PASS_TIMEOUT_SECONDS")
        or DEFAULT_PASS_TIMEOUT_S
    )
    try:
        value = float(source)
    except (TypeError, ValueError):
        return float(DEFAULT_PASS_TIMEOUT_S)
    return max(10.0, value)


def resolve_retry_config() -> Dict[str, Union[int, float]]:
    """Collect retry configuration sourced from environment variables."""

    return {
        "temperature": _float_from_env(
            "LLM_PASS_TEMPERATURE", DEFAULT_PASS_TEMPERATURE
        ),
        "max_tokens": _int_from_env("LLM_PASS_MAX_TOKENS", DEFAULT_PASS_MAX_TOKENS),
        "max_attempts": max(1, _int_from_env("LLM_PASS_MAX_ATTEMPTS", DEFAULT_PASS_MAX_ATTEMPTS)),
        "initial_backoff_ms": _int_from_env(
            "LLM_PASS_BACKOFF_INITIAL_MS",
            _int_from_env("LLM_BACKOFF_INITIAL_MS", DEFAULT_PASS_BACKOFF_INITIAL_MS),
        ),
        "backoff_factor": _float_from_env(
            "LLM_PASS_BACKOFF_FACTOR",
            _float_from_env("LLM_BACKOFF_FACTOR", DEFAULT_PASS_BACKOFF_FACTOR),
        ),
        "backoff_max_ms": _int_from_env(
            "LLM_PASS_BACKOFF_MAX_MS",
            _int_from_env("LLM_BACKOFF_MAX_MS", DEFAULT_PASS_BACKOFF_MAX_MS),
        ),
    }
