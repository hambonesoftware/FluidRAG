# backend/parse/header_detector.py
# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Tuple, Dict, List, Optional
from dataclasses import dataclass
import re

from .patterns_rfq import RFQ_SECTION_RES, UNIT_NEARBY_RX, ADDRESS_HINT_RX, PAGE_ART_RX

HEADER_RX = re.compile(r'^\s*(\d+(?:\.\d+)*)\s*(?:[-:]|\s+)\s*(.+?)\s*$')
ALT_HEADER_RX = re.compile(r'^\s*Section\s+(\d+(?:\.\d+)*)\s*[-:]?\s*(.+?)\s*$', re.IGNORECASE)
ALLCAPS_HEADER_RX = re.compile(r'^[A-Z0-9][A-Z0-9\s\-/&,\.]{4,}$')

def is_header_line(line: str, style: Dict | None = None) -> Tuple[bool, Dict]:
    style = style or {}
    txt = (line or '').strip()
    if not (6 <= len(txt) <= 160):
        return (False, {'reason': 'length'})
    if ADDRESS_HINT_RX.search(txt) or PAGE_ART_RX.search(txt):
        return (False, {'reason': 'address_or_page'})

    def score(style: Dict, txt: str, penalty: int) -> int:
        letters = [c for c in txt if c.isalpha()]
        caps_ratio = (sum(c.isupper() for c in letters) / max(1, len(letters))) if letters else 0.0
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
        return (True, {'regex': 'allcaps', 'penalty': 0})

    return (False, {'reason': 'no_match'})

def score_header_candidate(line: str, style: dict | None = None) -> float:
    """
    Heuristic score: regex hits, numbering depth, font/style boosts, disqualifier penalties.
    Accept if score >= CONFIG.accept_score_threshold; ambiguous if between thresholds.
    """
    style = style or {}
    txt = (line or '').strip()
    if not txt:
        return -99.0

    score = 0.0

    # Base: whether our primary detector considers it a header
    ok, _meta = is_header_line(txt, style=style)
    if ok:
        score += 2.0

    # Numbering depth bonus (e.g., 1.2.3)
    depth = txt.count('.')
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
    if UNIT_NEARBY_RX.search(txt):
        score -= 2.0
    if ADDRESS_HINT_RX.search(txt):
        score -= 2.0
    if PAGE_ART_RX.search(txt):
        score -= 2.0

    # Very long single-line paragraphs without numbering are unlikely headers
    if len(txt) > 140 and depth == 0:
        score -= 1.0

    return score


@dataclass
class ScoreBreakdown:
    text: str
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
    txt = (line or "").strip()
    if not txt:
        return ScoreBreakdown(
            text="",
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
        if rx.search(txt):
            regex_hits.append(rx.pattern)
    if ALLCAPS_HEADER_RX.match(txt):
        regex_hits.append("ALLCAPS_HEADER_RX")

    ok, meta = is_header_line(txt, style=style)
    if ok:
        score += 2.0
        partial["is_header_line"] = 2.0
    else:
        partial["is_header_line"] = 0.0

    section_number: Optional[str] = None
    if isinstance(meta, dict):
        section_number = meta.get("section_number")
    if not section_number:
        match = re.match(r"^\s*([A-Za-z]\d+(?:\.\d+)*)", txt)
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

    caps_hit = bool(ALLCAPS_HEADER_RX.match(txt))

    if UNIT_NEARBY_RX.search(txt):
        penalty = -2.0
        score += penalty
        disqualifiers.append("units")
        partial["units_penalty"] = penalty
    if ADDRESS_HINT_RX.search(txt):
        penalty = -2.0
        score += penalty
        disqualifiers.append("address")
        partial["address_penalty"] = penalty
    if PAGE_ART_RX.search(txt):
        penalty = -2.0
        score += penalty
        disqualifiers.append("page_art")
        partial["page_art_penalty"] = penalty

    if len(txt) > 140 and not depth:
        penalty = -1.0
        score += penalty
        disqualifiers.append("long_line")
        partial["long_line_penalty"] = penalty

    return ScoreBreakdown(
        text=txt,
        regex_hits=regex_hits,
        numbering_depth=depth,
        font_size=font_size,
        bold=style.get("bold"),
        caps=caps_hit,
        disqualifiers=disqualifiers,
        partial_scores=partial,
        total=score,
    )
