"""Regex-driven header candidate extraction."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .....util.logging import get_logger

logger = get_logger(__name__)

_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (
        re.compile(
            r"^(?:appendix|chapter|section)\s+[A-Z\d]+(?:[\.\-][A-Z\d]+)*(?:\b|\s|:)",
            re.I,
        ),
        0.9,
    ),
    (re.compile(r"^\d+(?:\.\d+)+\s+", re.I), 0.85),
    (re.compile(r"^\d+[\.)]\s+", re.I), 0.72),
    (re.compile(r"^[A-Z]\d+(?:[\.\-]\d+)*\b", re.I), 0.75),
    (re.compile(r"^(?:[IVXLCM]+\.)+\s+", re.I), 0.7),
    (
        re.compile(
            r"^(executive summary|introduction|overview|conclusion)\b",
            re.I,
        ),
        0.62,
    ),
    (re.compile(r"^[A-Z][A-Z\s]{4,}$"), 0.65),
]

_WHITESPACE = re.compile(r"\s+")
_SLUG = re.compile(r"[^A-Za-z0-9]+")
_INLINE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?P<header>(?:appendix|chapter|section)\s+[A-Z\d]+(?:[\.\-][A-Z\d]+)*(?:\s+[A-Z][^\.\n;:]{0,60})?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<header>[A-Z]?\d+(?:\.\d+)*(?:[\.)])?\s+[A-Z][^\.\n;:]{0,60})",
        re.IGNORECASE,
    ),
]


_WORD_PATTERN = re.compile(r"[A-Za-z]{1,}")
_MEASURE_UNITS = {
    "hz",
    "khz",
    "mhz",
    "ghz",
    "db",
    "dba",
    "dbm",
    "vac",
    "vdc",
    "amp",
    "amps",
    "a",
    "v",
    "kv",
    "mw",
    "kw",
    "hp",
    "lb",
    "lbs",
    "kg",
    "g",
    "mm",
    "cm",
    "m",
    "in",
    "ft",
    "psi",
    "scfm",
    "rpm",
    "%",
    "°c",
    "°f",
}


def _has_meaningful_alpha(text: str) -> bool:
    words = _WORD_PATTERN.findall(text)
    if not words:
        return False
    for word in words:
        if any(char.islower() for char in word) and len(word) >= 3:
            return True
        if word.lower() in {"appendix", "chapter", "section"}:
            return True
    return False


def _looks_like_measurement(text: str) -> bool:
    candidate = text.strip().lower().strip(".:;)")
    if not candidate:
        return False
    match = re.match(r"^[\d\s.,/\-]+(?P<unit>[a-z°%]+)$", candidate)
    if match and match.group("unit") in _MEASURE_UNITS:
        return True
    parts = candidate.split()
    if len(parts) == 2:
        number, unit = parts
        try:
            float(number.replace(",", ""))
        except ValueError:
            return False
        unit = unit.strip("()%")
        if unit in _MEASURE_UNITS:
            return True
    return False


def _is_viable_header(text: str) -> bool:
    candidate = text.strip()
    if len(candidate) < 3:
        return False
    if not _has_meaningful_alpha(candidate):
        return False
    if _looks_like_measurement(candidate):
        return False
    return True


def _uppercase_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def _series_key(text: str) -> tuple[str, int | None, int]:
    normalized = _WHITESPACE.sub(" ", text.strip())
    if not normalized:
        return "root", None, 1
    prefixed = re.match(
        r"^(?P<prefix>appendix|chapter|section)\s+(?P<body>[A-Z\d]+(?:[\.\-][A-Z\d]+)*)",
        normalized,
        flags=re.IGNORECASE,
    )
    if prefixed:
        body = prefixed.group("body")
        numbers = [int(part) for part in re.findall(r"\d+", body)]
        ordinal = numbers[-1] if numbers else None
        level = max(len(numbers), 1)
        return f"{prefixed.group('prefix').title()} {body.upper()}", ordinal, level
    numeric = re.match(r"^(?P<body>\d+(?:\.\d+)*)", normalized)
    if numeric:
        body = numeric.group("body").rstrip(".")
        parts = [int(part) for part in body.split(".") if part]
        ordinal = parts[-1] if parts else None
        level = max(len(parts), 1)
        return body or normalized, ordinal, level
    alpha = re.match(r"^(?P<head>[A-Z])(?:[\.\-](?P<tail>\d+))+", normalized)
    if alpha:
        numbers = [int(part) for part in re.findall(r"\d+", alpha.group(0))]
        ordinal = numbers[-1] if numbers else None
        level = max(len(numbers), 1)
        return alpha.group(0).upper(), ordinal, level
    roman = re.match(r"^(?P<roman>[IVXLCM]+)\.", normalized, flags=re.IGNORECASE)
    if roman:
        return roman.group("roman").upper(), None, 1
    slug = _SLUG.sub("-", normalized.upper()).strip("-")
    return slug or "root", None, 1


def _base_score(text: str) -> float:
    normalized = text.strip()
    score = 0.0
    for pattern, weight in _PATTERNS:
        if pattern.search(normalized):
            score = max(score, weight)
    if _uppercase_ratio(normalized) >= 0.65:
        score = max(score, 0.55)
    if normalized.endswith(":"):
        score = max(score, 0.6)
    if len(normalized.split()) <= 6:
        score = max(score, score + 0.05)
    return min(score, 0.95)


def _extract_inline_headers(text: str) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    for pattern in _INLINE_PATTERNS:
        for match in pattern.finditer(text):
            header_text = match.group("header").strip(" .:-)\n")
            header_text = _trim_header_text(header_text)
            if not header_text:
                continue
            if not _is_viable_header(header_text):
                continue
            key = (match.start(), header_text.lower())
            if key in seen:
                continue
            seen.add(key)
            results.append((match.start(), header_text))
    results.sort(key=lambda item: item[0])
    return results


def _trim_header_text(value: str) -> str:
    tokens = [tok for tok in value.split() if tok not in {"-", "–"}]
    if not tokens:
        return value.strip()
    first = tokens[0]
    if first.lower() in {"appendix", "chapter", "section"}:
        limit = min(len(tokens), 3)
    elif re.match(r"^[A-Z]?\d", first):
        limit = min(len(tokens), 2)
    else:
        limit = min(len(tokens), 4)
    return " ".join(tokens[:limit])


def find_header_candidates(chunks_artifact_path: str) -> list[dict[str, Any]]:
    """Detect header candidates with patterns (A.1, Appendix A-1, etc.)."""

    path = Path(chunks_artifact_path)
    if not path.exists():
        logger.warning(
            "headers.regex.missing_chunks", extra={"path": chunks_artifact_path}
        )
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.error(
            "headers.regex.read_failed",
            extra={"path": chunks_artifact_path, "error": str(exc)},
        )
        return []

    candidates: list[dict[str, Any]] = []
    for index, line in enumerate(line for line in lines if line):
        try:
            chunk = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("headers.regex.invalid_row", extra={"line_index": index})
            continue
        text = str(chunk.get("text", "")).strip()
        if not text:
            continue
        normalized_text = text.replace("–", "-")
        inline_headers = _extract_inline_headers(normalized_text)
        if inline_headers:
            base_sentence = int(chunk.get("sentence_start", index))
            for offset, (_, header_value) in enumerate(inline_headers, start=1):
                header_score = _base_score(header_value)
                if header_score < 0.35:
                    continue
                section_key, ordinal, level = _series_key(header_value)
                candidate_inline: dict[str, Any] = {
                    "chunk_id": chunk.get("chunk_id"),
                    "doc_id": chunk.get("doc_id"),
                    "text": header_value,
                    "raw_text": header_value,
                    "score": header_score,
                    "score_regex": header_score,
                    "typography": chunk.get("typography", {}),
                    "sentence_start": base_sentence + offset,
                    "sentence_end": base_sentence + offset,
                    "chunk_index": index * 100 + offset,
                    "section_key": section_key,
                    "ordinal": ordinal,
                    "level": level,
                    "chunk_ids": (
                        [chunk.get("chunk_id")] if chunk.get("chunk_id") else []
                    ),
                    "recovered": False,
                }
                candidates.append(candidate_inline)
            continue
        if not _is_viable_header(normalized_text):
            continue
        base_score = _base_score(normalized_text)
        if base_score < 0.4 and base_score < 0.25:
            continue
        section_key, ordinal, level = _series_key(normalized_text)
        candidate: dict[str, Any] = {
            "chunk_id": chunk.get("chunk_id"),
            "doc_id": chunk.get("doc_id"),
            "text": text,
            "raw_text": text,
            "score": base_score,
            "score_regex": base_score,
            "typography": chunk.get("typography", {}),
            "sentence_start": int(chunk.get("sentence_start", index)),
            "sentence_end": int(chunk.get("sentence_end", index)),
            "chunk_index": index,
            "section_key": section_key,
            "ordinal": ordinal,
            "level": level,
            "chunk_ids": [chunk.get("chunk_id")] if chunk.get("chunk_id") else [],
            "recovered": False,
        }
        candidates.append(candidate)
    logger.debug(
        "headers.regex.candidates",
        extra={"path": chunks_artifact_path, "candidates": len(candidates)},
    )
    return candidates


__all__ = ["find_header_candidates"]
