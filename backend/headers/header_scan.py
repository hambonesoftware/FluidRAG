"""Header candidate scanning and promotion helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence

import re

from backend.headers.config import HEADER_GATE_MODE
from backend.uf_chunker import HEADER_PATTERN, UFChunk

# Strong patterns that should always auto-promote regardless of EFHG scores.
STRONG_PATTERNS = {
    "numeric_section",
    "appendix_top",
    "appendix_sub_AN",
    "appendix_sub_AlN",
}

_PATTERN_CHECKS = {
    "numeric_section": re.compile(r"^\s*\d+\)\s+.+$"),
    "appendix_top": re.compile(
        r"(?i)^\s*(appendix|annex)\s+[A-Z]\b(?:\s*[—\-: ]\s*.+)?$"
    ),
    "appendix_sub_AN": re.compile(r"^\s*[A-Z]\d{1,3}\.\s+.+$"),
    "appendix_sub_AlN": re.compile(r"^\s*[A-Z]\.\d{1,3}\s+.+$"),
}

_LABEL_ONLY_CHECKS = {
    "numeric_section": re.compile(r"^\s*\d+\)\s*$"),
    "appendix_top": re.compile(r"(?i)^\s*(appendix|annex)\s+[A-Z]\s*$"),
    "appendix_sub_AN": re.compile(r"^\s*[A-Z]\d{1,3}\.?\s*$"),
    "appendix_sub_AlN": re.compile(r"^\s*[A-Z]\.\d{1,3}\s*$"),
}

_PATTERN_FINDER = {
    "numeric_section": re.compile(r"\d+\)"),
    "appendix_top": re.compile(r"(?i)\b(?:appendix|annex)\b"),
    "appendix_sub_AN": re.compile(r"\b[A-Z]\d{1,3}\."),
    "appendix_sub_AlN": re.compile(r"\b[A-Z]\.\d{1,3}"),
}


@dataclass
class HeaderCandidate:
    """Represents a single line (or inline segment) that resembles a header."""

    chunk_id: str
    chunk_index: int
    page: int
    line_index: int
    text: str
    pattern: str
    label: str
    start_char: int
    end_char: int
    style: Dict[str, object] = field(default_factory=dict)
    candidate_id: int = -1
    promoted: bool = False
    promotion_reason: str | None = None
    total: float = 0.0

    def to_dict(self) -> Dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "chunk_id": self.chunk_id,
            "chunk_index": self.chunk_index,
            "page": self.page,
            "line_index": self.line_index,
            "text": self.text,
            "pattern": self.pattern,
            "label": self.label,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "style": dict(self.style),
            "promoted": self.promoted,
            "promotion_reason": self.promotion_reason,
            "score_total": self.total,
        }


def _scan_line(
    chunk: UFChunk,
    chunk_index: int,
    line_index: int,
    base_offset: int,
    raw_line: str,
) -> Iterable[HeaderCandidate]:
    """Yield header candidates discovered within a single chunk line."""

    # Normalise the line for scanning but retain original characters for offsets.
    line = raw_line.rstrip("\r\n")
    if not line:
        return []

    results: List[HeaderCandidate] = []
    for pattern, finder in _PATTERN_FINDER.items():
        check = _PATTERN_CHECKS[pattern]
        for match in finder.finditer(line):
            seg = line[match.start() :]
            if not seg:
                continue
            trimmed = seg.lstrip()
            if not trimmed:
                continue
            if not check.match(trimmed):
                label_only = _LABEL_ONLY_CHECKS.get(pattern)
                if not label_only or not label_only.match(trimmed):
                    continue
            leading_ws = len(seg) - len(trimmed)
            rel_offset = base_offset + match.start() + leading_ws
            start_char = chunk.span_char[0] + rel_offset
            end_char = start_char + len(trimmed)
            label_match = HEADER_PATTERN.match(trimmed)
            label = label_match.group(0).strip() if label_match else trimmed.split(" ")[0]
            candidate = HeaderCandidate(
                chunk_id=chunk.id,
                chunk_index=chunk_index,
                page=chunk.page,
                line_index=line_index,
                text=trimmed,
                pattern=pattern,
                label=label,
                start_char=int(start_char),
                end_char=int(end_char),
                style=dict(chunk.style or {}),
            )
            results.append(candidate)
            # Avoid emitting duplicate candidates for the same segment by
            # breaking after the first anchored match per pattern.
            break
    return results


def scan_candidates(chunks: Sequence[UFChunk]) -> List[HeaderCandidate]:
    """Scan UF chunks and emit raw header candidates."""

    candidates: List[HeaderCandidate] = []
    for chunk_index, chunk in enumerate(chunks):
        text = chunk.text or ""
        if not text.strip():
            continue
        offset = 0
        for line_index, line in enumerate(text.splitlines(keepends=True)):
            found = list(_scan_line(chunk, chunk_index, line_index, offset, line))
            candidates.extend(found)
            offset += len(line)
    for idx, candidate in enumerate(candidates):
        candidate.candidate_id = idx
    return candidates


def promote_candidates(
    candidates: Sequence[HeaderCandidate],
    gate_mode: str | None = None,
) -> List[HeaderCandidate]:
    """Apply promotion rules to header candidates."""

    gate = gate_mode or HEADER_GATE_MODE
    promoted: List[HeaderCandidate] = []
    for candidate in candidates:
        if candidate.pattern in STRONG_PATTERNS:
            candidate.promoted = True
            candidate.promotion_reason = "pattern"
            promoted.append(candidate)
        else:
            if gate == "score_gate":
                candidate.promoted = candidate.total > 0.0
            else:
                candidate.promoted = False
    return promoted


__all__ = [
    "HeaderCandidate",
    "STRONG_PATTERNS",
    "scan_candidates",
    "promote_candidates",
]
