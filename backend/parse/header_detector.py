# backend/parse/header_detector.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Tuple, Dict, List, Optional
from dataclasses import dataclass
import re
import unicodedata

from .patterns_rfq import (
    RFQ_SECTION_RES,
    UNIT_NEARBY_RX,
    ADDRESS_HINT_RX,
    PAGE_ART_RX,
    APPENDIX_TOLERANT_PATTERN,
)

HEADER_RX = re.compile(r'^\s*(\d+(?:\.\d+)*)\s*(?:[-:]|\s+)\s*(.+?)\s*$')
ALT_HEADER_RX = re.compile(r'^\s*Section\s+(\d+(?:\.\d+)*)\s*[-:]?\s*(.+?)\s*$', re.IGNORECASE)
ALLCAPS_HEADER_RX = re.compile(r'^[A-Z0-9][A-Z0-9\s\-/&,\.]{4,}$')
APPENDIX_NUM_RX = re.compile(APPENDIX_TOLERANT_PATTERN)

_ALT_SPACE_CHARS = {
    "\u00A0",  # NBSP
    "\u2002",  # ENSP
    "\u2003",  # EMSP
    "\u202F",  # narrow NBSP
}
_ALT_DOT_CHARS = {"\u2024", "\u2027", "\uFF0E"}


def normalize_heading_text(line: str) -> str:
    if not line:
        return ""
    txt = unicodedata.normalize("NFKC", line)
    buf = []
    for ch in txt:
        if ch in _ALT_SPACE_CHARS:
            buf.append(" ")
        elif ch in _ALT_DOT_CHARS:
            buf.append(".")
        else:
            buf.append(ch)
    normalized = "".join(buf)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _caps_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(c.isupper() for c in letters) / len(letters)

def is_header_line(line: str, style: Dict | None = None) -> Tuple[bool, Dict]:
    style = style or {}
    raw_txt = (line or '').strip()
    txt = normalize_heading_text(raw_txt)
    if not (6 <= len(txt) <= 160):
        return (False, {'reason': 'length'})
    if ADDRESS_HINT_RX.search(txt) or PAGE_ART_RX.search(txt):
        return (False, {'reason': 'address_or_page'})

    def score(style: Dict, txt: str, penalty: int) -> int:
        caps_ratio = _caps_ratio(txt)
        style_score = 0
        if style.get('font_sigma_rank', 0) is not None and style.get('font_sigma_rank', 0) >= 1.5:
            style_score += 2
        if style.get('bold', False):
            style_score += 1
        if caps_ratio >= 0.7:
            style_score += 1
        return style_score - penalty

    # Common numbering/section keyword
    for rx, label in [(HEADER_RX, 'dotnum'), (ALT_HEADER_RX, 'section_kw')]:
        if rx.match(txt):
            penalty = 2 if UNIT_NEARBY_RX.search(txt) else 0
            return (score(style, txt, penalty) >= 1, {'regex': label, 'penalty': penalty})

    # RFQ-specific patterns
    for rx in RFQ_SECTION_RES:
        if rx.match(txt):
            penalty = 2 if UNIT_NEARBY_RX.search(txt) else 0
            return (score(style, txt, penalty) >= 1, {'regex': 'rfq', 'penalty': penalty})

    # ALLCAPS fall-back (avoid unit-heavy lines)
    if ALLCAPS_HEADER_RX.match(txt) and not UNIT_NEARBY_RX.search(txt):
        if not txt or txt.endswith('.'):
            return (False, {'reason': 'allcaps_terminal_period'})
        tokens = [t for t in txt.split(' ') if t]
        if len(tokens) < 2 or any(len(t) <= 2 for t in tokens):
            return (False, {'reason': 'allcaps_short_token'})
        if _caps_ratio(txt) < 0.6:
            return (False, {'reason': 'allcaps_low_caps_ratio'})
        return (True, {'regex': 'allcaps', 'penalty': 0})

    return (False, {'reason': 'no_match'})

def score_header_candidate(line: str, style: dict | None = None) -> float:
    """
    Heuristic score: regex hits, numbering depth, font/style boosts, disqualifier penalties.
    Accept if score >= CONFIG.accept_score_threshold; ambiguous if between thresholds.
    """
    style = style or {}
    raw_txt = (line or '').strip()
    if not raw_txt:
        return -99.0

    score = 0.0

    normalized = normalize_heading_text(raw_txt)

    # Base: whether our primary detector considers it a header
    ok, _meta = is_header_line(raw_txt, style=style)
    if ok:
        score += 2.0

    # Numbering depth bonus (e.g., 1.2.3)
    depth = normalized.count('.')
    if depth >= 1:
        score += min(1.0 + 0.25 * depth, 2.0)

    # Typography votes
    fsr = float(style.get('font_sigma_rank', 0.0) or 0.0)
    if fsr >= 1.5:
        score += 1.5
    cr = float(style.get('caps_ratio', 0.0) or 0.0)
    if cr >= 0.65:
        score += 1.0
    if style.get('bold'):
        score += 0.5

    # Disqualifiers
    if UNIT_NEARBY_RX.search(normalized):
        score -= 2.0
    if ADDRESS_HINT_RX.search(normalized):
        score -= 2.0
    if PAGE_ART_RX.search(normalized):
        score -= 2.0

    # Very long single-line paragraphs without numbering are unlikely headers
    if len(normalized) > 140 and depth == 0:
        score -= 1.0

    return score


@dataclass
class ScoreBreakdown:
    text: str
    normalized_text: str
    regex_hits: List[str]
    numbering_depth: Optional[int]
    font_size: Optional[float]
    bold: Optional[bool]
    caps: bool
    disqualifiers: List[str]
    partial_scores: Dict[str, float]
    total: float


def score_header_candidate_debug(line: str, style: dict | None = None) -> ScoreBreakdown:
    """Return a structured breakdown of how a candidate line was scored."""
    style = style or {}
    raw_txt = (line or "").strip()
    normalized = normalize_heading_text(raw_txt)
    if not raw_txt:
        return ScoreBreakdown(
            text="",
            normalized_text="",
            regex_hits=[],
            numbering_depth=None,
            font_size=style.get("font_size"),
            bold=style.get("bold"),
            caps=False,
            disqualifiers=["empty"],
            partial_scores={},
            total=-99.0,
        )

    regex_hits: List[str] = []
    partial: Dict[str, float] = {}
    disqualifiers: List[str] = []
    score = 0.0

    # Mirror RFQ regex checks
    for rx in RFQ_SECTION_RES:
        if rx.search(normalized):
            regex_hits.append(rx.pattern)
    if ALLCAPS_HEADER_RX.match(normalized):
        regex_hits.append("ALLCAPS_HEADER_RX")

    ok, meta = is_header_line(raw_txt, style=style)
    if ok:
        score += 2.0
        partial["is_header_line"] = 2.0
    else:
        partial["is_header_line"] = 0.0

    section_number: Optional[str] = None
    if isinstance(meta, dict):
        section_number = meta.get("section_number")
    if not section_number:
        match = re.match(r"^\s*([A-Za-z]\d+(?:\.\d+)*)", normalized)
        if match:
            section_number = match.group(1)

    from .header_levels import numbering_depth

    depth = numbering_depth(section_number)
    if depth:
        boost = 0.5
        score += boost
        partial["numbering_depth"] = boost

    font_size = style.get("font_size")
    if font_size:
        boost = 0.5
        score += boost
        partial["font_size"] = boost

    if style.get("bold"):
        boost = 0.4
        score += boost
        partial["bold"] = boost

    caps_hit = bool(ALLCAPS_HEADER_RX.match(normalized))

    if UNIT_NEARBY_RX.search(normalized):
        penalty = -2.0
        score += penalty
        disqualifiers.append("units")
        partial["units_penalty"] = penalty
    if ADDRESS_HINT_RX.search(normalized):
        penalty = -2.0
        score += penalty
        disqualifiers.append("address")
        partial["address_penalty"] = penalty
    if PAGE_ART_RX.search(normalized):
        penalty = -2.0
        score += penalty
        disqualifiers.append("page_art")
        partial["page_art_penalty"] = penalty

    if len(normalized) > 140 and not depth:
        penalty = -1.0
        score += penalty
        disqualifiers.append("long_line")
        partial["long_line_penalty"] = penalty

    return ScoreBreakdown(
        text=raw_txt,
        normalized_text=normalized,
        regex_hits=regex_hits,
        numbering_depth=depth,
        font_size=font_size,
        bold=style.get("bold"),
        caps=caps_hit,
        disqualifiers=disqualifiers,
        partial_scores=partial,
        total=score,
    )
