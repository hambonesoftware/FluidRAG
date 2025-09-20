# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Dict, Any
import re

try:
    from rapidfuzz.fuzz import ratio as fuzz_ratio
except Exception:
    import difflib
    def fuzz_ratio(a, b): return int(100 * difflib.SequenceMatcher(None, a or "", b or "").ratio())

from .header_detector import is_header_line, score_header_candidate
from .header_levels import map_font_sizes_to_levels, infer_heading_level
from .header_config import CONFIG

MEASURE_RX = re.compile(r'\b(?:\d{1,4}(?:\.\d+)?)(?:\s*(?:mm|cm|m|in|inch|ft|°c|°f|a|v|hz|psi|kpa|ip\d{2}))\b', re.I)
ADDRESS_RX = re.compile(r'\b(?:Street|St\.|Road|Rd\.|Drive|Dr\.|Ave\.|Avenue|Suite|USA|Tel|Fax)\b', re.I)
TOO_LONG_RX = re.compile(r'^\s*.{161,}\s*$')

def _caps_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    return (sum(c.isupper() for c in letters) / max(1, len(letters))) if letters else 0.0

def _looks_like_header_text(txt: str) -> bool:
    if not (6 <= len(txt) <= 160):       # keep in sync with header_detector
        return False
    if ADDRESS_RX.search(txt):
        return False
    if MEASURE_RX.search(txt):
        # Measurements often appear in specs lines; penalize
        return False
    if TOO_LONG_RX.match(txt):
        return False
    return True

def select_candidates(page_lines: List[str], page_styles: List[dict]) -> List[dict]:
    cands = []
    font_sizes = [(s or {}).get("font_size") for s in (page_styles or []) if (s or {}).get("font_size") is not None]
    size_map = map_font_sizes_to_levels(font_sizes, max_levels=4) if CONFIG.get("use_font_clusters", True) else {}

    for idx, raw in enumerate(page_lines or []):
        line = (raw or "").strip()
        if not line:
            continue

        style = (page_styles[idx] if page_styles and idx < len(page_styles) else {}) or {}
        if not _looks_like_header_text(line):
            continue

        s = score_header_candidate(line, style)
        if s < CONFIG.get("ambiguous_score_threshold", 1.10):
            continue

        caps = _caps_ratio(line)
        # Light boost for ALLCAPS or Title Case
        if caps >= 0.75:
            s += 0.25

        # Extract a plausible section number prefix if it exists
        m = re.search(r"^\s*([A-Z]|Appendix\s+[A-Z]|\d+(?:\.\d+)*|\d+\))", line, flags=re.IGNORECASE)
        section_number = (m.group(1) if m else "").strip()

        level = infer_heading_level(style.get("font_size"), section_number, size_map)
        cands.append({
            "line_idx": idx,
            "text": line,
            "style": {
                "font_sigma_rank": style.get("font_sigma_rank"),
                "bold": style.get("bold"),
                "caps_ratio": caps,
                "font_size": style.get("font_size"),
            },
            "score": s,
            "section_number": section_number,
            "level": level,
        })

    # Dedup near-duplicates (within a page) by fuzzy ratio
    cands.sort(key=lambda x: (-x["score"], x["line_idx"]))
    deduped, seen_text = [], []
    for c in cands:
        if seen_text and fuzz_ratio(seen_text[-1], c["text"]) >= CONFIG.get("dedup_fuzzy_threshold", 90):
            # keep the higher score already in deduped
            continue
        deduped.append(c)
        seen_text.append(c["text"])

    return deduped[: CONFIG.get("max_candidates_per_page", 40)]


def build_adjudication_prompt(page_text: str, candidates: List[dict], context_chars: int) -> str:
    # Single-page prompt
    def window_around_line(text: str, target: str, chars: int = 600) -> str:
        pos = text.find(target[:120])
        if pos < 0:
            return text[:chars]
        start = max(0, pos - chars // 2)
        end = min(len(text), pos + len(target) + chars // 2)
        return text[start:end]

    blob = "\n".join(page_text.splitlines())
    lines = [f"- [{c['line_idx']}]: {c['text']}" for c in candidates]
    ctxs  = [f"[{c['line_idx']}]: {window_around_line(blob, c['text'], chars=context_chars)}" for c in candidates]

    return (
        "You are validating section headings in an engineering RFQ/spec. "
        "Return ONLY JSON list: [{\"section_number\":\"\",\"section_name\":\"\",\"line_idx\":0}]. No prose.\n\n"
        "CANDIDATE_LINES:\n" + "\n".join(lines) + "\n\n" +
        "PAGE_TEXT_SNIPPETS:\n" + "\n".join(ctxs)
    )
