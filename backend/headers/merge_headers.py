from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple

from backend.models.headers import FinalHeader, HeaderCandidate


def _strip_leading_numbering(title: str, section_id: Optional[str]) -> str:
    text = (title or "").strip()
    if not text:
        return text
    if section_id:
        escaped = re.escape(section_id.strip())
        match = re.match(rf"^{escaped}[\s\.).:-]*", text, flags=re.IGNORECASE)
        if match:
            remainder = text[match.end():].strip()
            if remainder:
                return remainder
    match_generic = re.match(r"^[A-Za-z]?\d+[\s\.).:-]+(.+)$", text)
    if match_generic:
        candidate = match_generic.group(1).strip()
        if candidate:
            return candidate
    return text


def normalize_section_id(section_id: Optional[str], title: str) -> Optional[str]:
    if section_id:
        token = re.sub(r"\s+", "", str(section_id))
        token = token.replace("Section", "").replace("section", "")
        token = token.replace(":", "")
        token = token.strip()
        return token or None
    match = re.match(r"^\s*([A-Z]\d+|\d+(?:\.\d+)+|[A-Z]\.\d+)\b", title)
    if match:
        return match.group(1)
    return None


def normalize_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", title or "").strip().rstrip(".")
    return cleaned.lower()


def _candidate_score(candidate: HeaderCandidate) -> float:
    llm_conf = candidate.judging.llm_confidence
    heur_conf = candidate.judging.heuristic_confidence
    values = [v for v in (llm_conf, heur_conf) if isinstance(v, (int, float))]
    if values:
        base = sum(values) / len(values)
    else:
        base = 0.5
    if candidate.source == "heuristic":
        base += 0.05
    return max(0.0, min(1.0, float(base)))


def merge_candidates(
    llm_candidates: Iterable[HeaderCandidate],
    heuristic_candidates: Iterable[HeaderCandidate],
) -> List[FinalHeader]:
    buckets: Dict[Tuple[Optional[str], str], List[HeaderCandidate]] = {}

    def key_for(candidate: HeaderCandidate) -> Tuple[Optional[str], str]:
        norm_id = normalize_section_id(candidate.section_id, candidate.title)
        norm_title = normalize_title(candidate.title)
        if norm_id:
            return (norm_id, "")
        return (None, norm_title)

    for candidate in list(llm_candidates) + list(heuristic_candidates):
        buckets.setdefault(key_for(candidate), []).append(candidate)

    finals: List[FinalHeader] = []
    for (norm_id, norm_title), group in buckets.items():
        sources = sorted({cand.source for cand in group})
        representative = max(group, key=_candidate_score)
        page = representative.page
        span_char = representative.span_char
        level = next((cand.level for cand in group if cand.level is not None), None)
        heuristic_title = next(
            (cand.title for cand in group if cand.source == "heuristic" and cand.title),
            None,
        )
        if heuristic_title:
            title_choice = heuristic_title
        else:
            title_choice = representative.title
        title_choice = _strip_leading_numbering(title_choice, norm_id)

        all_scores = [_candidate_score(cand) for cand in group]
        merged_conf = sum(all_scores) / len(all_scores) if all_scores else 0.5
        reasons: List[str] = []

        def add_reason(value: str | None) -> None:
            if not value:
                return
            if value not in reasons:
                reasons.append(value)

        for source in sources:
            add_reason(f"source:{source}")

        for cand in group:
            cand_reasons = getattr(cand.judging, "reasons", None) or []
            for reason in cand_reasons:
                add_reason(f"{cand.source}:{reason}")

        if len(sources) > 1:
            merged_conf = min(1.0, merged_conf + 0.1)
            add_reason("supported_by_both_sources")

        finals.append(
            FinalHeader(
                section_id=norm_id,
                title=title_choice,
                level=level,
                page=page,
                span_char=span_char,
                sources=sources,
                confidence=merged_conf,
                reasons=reasons,
            )
        )

    def sort_key(header: FinalHeader):
        section = header.section_id or ""
        if section and re.match(r"^\d+(?:\.\d+)*$", section):
            parts = [int(part) for part in section.split(".")]
            return (0, parts, header.page or 10**9, header.title.lower())
        return (1, [ord(c) for c in section], header.page or 10**9, header.title.lower())

    finals.sort(key=sort_key)
    return finals


__all__ = ["merge_candidates", "normalize_section_id", "normalize_title"]
