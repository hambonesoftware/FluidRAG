"""High-evidence passage selector."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

from .context import RAGContext
from .utils import extract_key_values

_MODAL_PAT = re.compile(r"\b(shall|must|required|should)\b", re.IGNORECASE)


def _count_units(text: str, patterns: Iterable[str]) -> int:
    return sum(1 for pat in patterns if re.search(rf"\b{re.escape(pat)}\b", text, re.IGNORECASE))


def _count_standards(text: str, standards: Iterable[str]) -> int:
    return sum(1 for std in standards if std.lower() in text.lower())


def _table_proximity(text: str) -> float:
    return 1.0 if re.search(r"table\s*\d+|appendix", text, re.IGNORECASE) else 0.0


def _modal_strength(text: str) -> float:
    return len(_MODAL_PAT.findall(text))


def _score_sentence(sentence: str, weights: Dict[str, float], entropy_delta: float, cfg: Dict[str, Any]):
    units = _count_units(sentence, cfg.get("unit_patterns", []))
    standards = _count_standards(sentence, cfg.get("standard_ids", []))
    modals = _modal_strength(sentence)
    table = _table_proximity(sentence)
    return (
        weights.get("entropy_delta", 0.0) * entropy_delta
        + weights.get("nums_units", 0.0) * units
        + weights.get("standards", 0.0) * standards
        + weights.get("modal_shall", 0.0) * modals
        + weights.get("table_proximity", 0.0) * table
    )


def select_hep_passages(sections_or_fluid, profile, context: RAGContext):
    cfg = profile.get("hep_scoring", {})
    weights = cfg.get("weights", {})
    topn = cfg.get("topN_per_section", 3)

    outputs: List[Dict[str, Any]] = []
    for section in sections_or_fluid:
        text = section.get("text") or section.get("section_name") or ""
        if not text:
            continue
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        entropy_traces = section.get("signals", {}).get("delta_entropy", [])
        entropy_val = 0.0
        if entropy_traces:
            entropy_val = max(entropy_traces)
        scored: List[Tuple[float, str]] = []
        for sent in sentences:
            score = _score_sentence(sent, weights, entropy_val, cfg)
            if score <= 0:
                continue
            scored.append((score, sent))
        scored.sort(reverse=True, key=lambda x: x[0])
        for score, sent in scored[:topn]:
            key_values = extract_key_values(sent)
            outputs.append(
                {
                    "text": sent,
                    "score": score,
                    "section_id": section.get("section_id") or section.get("provenance", [None])[0],
                    "anchors": section.get("anchors", []),
                    "pages": section.get("pages") or [section.get("page_start")],
                    "provenance": section.get("provenance") or [section.get("section_id")],
                    "key_values": key_values,
                    "resolution": "hep",
                }
            )
    return outputs
