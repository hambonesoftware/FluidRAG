from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional

from backend.models.headers import HeaderCandidate, Judging

_NUMBER_PREFIX = re.compile(
    r"^(?P<section>(?:\d+(?:\.\d+)*|[A-Za-z]\d{1,3}|[A-Za-z]\.\d{1,3}|(?:appendix|annex)\s+[A-Z]))[\s\.).:-]*",
    re.IGNORECASE,
)


def _infer_section_id(title: str, fallback: Optional[str] = None) -> Optional[str]:
    if fallback:
        return str(fallback).strip() or None
    match = _NUMBER_PREFIX.match(title)
    if not match:
        return None
    section = match.group("section") or ""
    section = section.strip()
    if not section:
        return None
    # Normalise Appendix/Annex prefixes
    lowered = section.lower()
    if lowered.startswith("appendix") or lowered.startswith("annex"):
        parts = section.split()
        if len(parts) >= 2:
            return f"{parts[0].title()} {parts[1].upper()}"
    return section


def _typography_score(record: Mapping[str, Any], font_ranks: Dict[float, int] | None) -> Optional[float]:
    try:
        font_size = float(record.get("font_size"))
    except Exception:
        font_size = None
    rank = None
    if font_ranks and font_size is not None:
        rank = font_ranks.get(round(font_size, 2))
    if rank is None:
        rank = record.get("level_font")
    try:
        rank_value = int(rank) if rank is not None else None
    except Exception:
        rank_value = None
    if rank_value is None or rank_value <= 0:
        return None
    return max(0.0, min(1.0, 1.0 / float(rank_value)))


def _heuristic_confidence(record: Mapping[str, Any]) -> float:
    base = 0.55
    if record.get("is_bold"):
        base += 0.1
    if record.get("level_numbering"):
        base += 0.15
    if record.get("level") and isinstance(record.get("level"), int):
        base += 0.05
    return max(0.0, min(1.0, base))


def run_heuristic_header_pass(
    heuristic_records: List[Dict[str, Any]],
    doc_meta: Optional[Dict[str, Any]] = None,
) -> List[HeaderCandidate]:
    """Convert raw heuristic header rows into :class:`HeaderCandidate` objects."""

    font_ranks = None
    if doc_meta:
        raw_ranks = doc_meta.get("font_rank")
        if isinstance(raw_ranks, dict):
            font_ranks = {
                float(k) if not isinstance(k, float) else k: int(v)
                for k, v in raw_ranks.items()
                if isinstance(v, (int, float))
            }

    candidates: List[HeaderCandidate] = []
    for record in heuristic_records:
        title = str(record.get("text") or "").strip()
        if not title:
            continue

        page = record.get("page")
        try:
            page_num = int(page) if page is not None else None
        except Exception:
            page_num = None

        level = record.get("level")
        try:
            level_val = int(level) if level is not None else None
        except Exception:
            level_val = None

        section_id = _infer_section_id(title, record.get("section_number"))

        typo_score = _typography_score(record, font_ranks)
        conf = _heuristic_confidence(record)
        pattern_id = None
        reasons: List[str] = []
        if record.get("level_numbering"):
            pattern_id = "numbering"
            reasons.append("numeric_pattern")
        if record.get("is_bold"):
            reasons.append("bold_text")
        if typo_score:
            reasons.append("large_font")

        judging = Judging(
            typography_score=typo_score,
            heuristic_confidence=conf,
            page=page_num,
            pattern_id=pattern_id,
            reasons=reasons,
        )

        candidates.append(
            HeaderCandidate(
                source="heuristic",
                section_id=section_id,
                title=title,
                level=level_val,
                page=page_num,
                span_char=None,
                judging=judging,
            )
        )

    return candidates


__all__ = ["run_heuristic_header_pass"]
