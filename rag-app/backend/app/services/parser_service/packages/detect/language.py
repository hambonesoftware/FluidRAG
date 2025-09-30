"""Language detection utilities with langdetect fallback."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from langdetect import DetectorFactory, LangDetectException, detect

_LATIN_PATTERN = re.compile(r"[a-zA-Z]")

# langdetect uses randomness internally; seed for determinism in tests
DetectorFactory.seed = 0


def _iter_text(pages: Iterable[dict[str, Any]]) -> str:
    return " ".join(page.get("text", "") for page in pages)


def detect_language(pages: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Detect language/script for document."""

    text = _iter_text(pages)
    if not text.strip():
        return {"code": "und", "confidence": 0.0, "method": "empty"}

    try:
        code = detect(text)
        return {"code": code, "confidence": 0.92, "method": "langdetect"}
    except LangDetectException:
        pass

    total = len(text)
    ascii_ratio = sum(1 for ch in text if ch.isascii()) / total
    latin_ratio = len(_LATIN_PATTERN.findall(text)) / total
    vowel_ratio = sum(1 for ch in text.lower() if ch in "aeiou") / total

    code = "en"
    confidence = min(
        1.0, (ascii_ratio * 0.4) + (latin_ratio * 0.4) + (vowel_ratio * 0.2)
    )
    if ascii_ratio < 0.5 and latin_ratio < 0.3:
        code = "und"
        confidence = 0.35
    return {"code": code, "confidence": round(confidence, 3), "method": "heuristic"}


__all__ = ["detect_language"]
