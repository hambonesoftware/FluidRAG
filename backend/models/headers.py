from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Judging:
    """Scoring metadata for header candidates from any source."""

    regex_match: Optional[float] = None
    typography_score: Optional[float] = None
    position_score: Optional[float] = None
    page: Optional[int] = None
    span_char: Optional[Tuple[int, int]] = None
    pattern_id: Optional[str] = None
    llm_confidence: Optional[float] = None
    llm_raw_fields: Dict[str, str] = field(default_factory=dict)
    heuristic_confidence: Optional[float] = None
    reasons: List[str] = field(default_factory=list)


@dataclass
class HeaderCandidate:
    """Unified representation of candidate headers from LLM or heuristics."""

    source: str  # "llm" or "heuristic"
    section_id: Optional[str]
    title: str
    level: Optional[int]
    page: Optional[int]
    span_char: Optional[Tuple[int, int]]
    judging: Judging = field(default_factory=Judging)


@dataclass
class FinalHeader:
    """Merged header entry after combining LLM and heuristic candidates."""

    section_id: Optional[str]
    title: str
    level: Optional[int]
    page: Optional[int]
    span_char: Optional[Tuple[int, int]]
    sources: List[str]
    confidence: float
    reasons: List[str] = field(default_factory=list)


__all__ = [
    "Judging",
    "HeaderCandidate",
    "FinalHeader",
]
