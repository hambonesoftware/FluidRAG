"""Selection helpers for section headers."""
from __future__ import annotations

import re
from typing import Callable, Dict, Iterable, List

from .header_match import classify_line
from .header_score import THRESHOLD, score_candidate


_ALT_SPACE_CHARS = {"\u00A0", "\u2002", "\u2003", "\u202F"}
_ALT_DOT_CHARS = {"\u2024", "\u2027", "\uFF0E"}
_SOFT_APPENDIX_PREFIX_RX = re.compile(r"^[A-Z]\d+[.\u2024\u2027\uFF0E]")
_SOFT_NUMERIC_PREFIX_RX = re.compile(r"^\d+\)")


def _normalize_soft_text(text: str) -> str:
    buf: List[str] = []
    for ch in text or "":
        if ch in _ALT_SPACE_CHARS:
            buf.append(" ")
        elif ch in _ALT_DOT_CHARS:
            buf.append(".")
        else:
            buf.append(ch)
    normalized = "".join(buf)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _should_apply_units_penalty(text: str) -> bool:
    stripped = _normalize_soft_text(text)
    if _SOFT_NUMERIC_PREFIX_RX.match(stripped):
        return False
    if _SOFT_APPENDIX_PREFIX_RX.match(stripped):
        return False
    return True


def select_headers(
    lines: Iterable[Dict],
    units_present_fn: Callable[[str], bool],
) -> List[Dict]:
    """Return the subset of ``lines`` that meet the deterministic threshold."""

    selections: List[Dict] = []

    for line in lines:
        text = line.get("text_norm", "")
        classification = classify_line(text, line.get("caps_ratio", 0.0))
        if classification["kind"] == "none":
            continue

        features = line.get("features", {})
        score, parts = score_candidate(classification["kind"], features)

        if (
            classification["kind"] == "label"
            and units_present_fn(text)
            and _should_apply_units_penalty(text)
        ):
            score -= 0.6
            parts["units_penalty"] = -0.6

        meets_threshold = score >= THRESHOLD
        record = {
            **line,
            **classification,
            "score": score,
            "partials": parts,
            "meets_threshold": meets_threshold,
        }
        selections.append(record)

    return [record for record in selections if record["meets_threshold"]]


__all__ = ["select_headers"]
