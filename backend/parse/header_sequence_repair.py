"""Aggressive deterministic header sequence repair utilities.

This module implements the *sequence repair* algorithm described in the
supplementary specification that accompanies the v1.7 header pipeline.  The
helpers operate on the verified header list emitted by the primary LLM header
pass and attempt to locate missing numbering entries (for example appendix
sections like ``A5.`` and ``A6.``) by performing targeted rescans of the
surrounding text.  The implementation is intentionally self contained so it
can be invoked directly from :mod:`backend.pipeline.preprocess` without
introducing a dependency on the legacy "sequence sanity" helpers.

The repair process is conservative – it only searches within the bounded
window between two verified headers and requires a direct text match inside the
original page text (either raw or normalised) before emitting a fix.  When a
header is recovered a structured record describing the provenance is returned
along with a confidence score so downstream components can audit the
intervention.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Normalisation helpers

_DOT_VARIANTS = "\u2024\u2027\uFF0E"
_SPACE_VARIANTS = "\u00A0\u2002\u2003\u2009\u200A\u202F\u205F\u3000"
_ZERO_WIDTH = "\u200B\u200C\u200D\uFEFF"


def _normalise_spaces(text: str) -> str:
    for ch in _SPACE_VARIANTS:
        text = text.replace(ch, " ")
    for ch in _ZERO_WIDTH:
        text = text.replace(ch, "")
    for ch in _DOT_VARIANTS:
        text = text.replace(ch, ".")
    return text


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalise(text: str) -> str:
    return _collapse_whitespace(_normalise_spaces(text or ""))


# ---------------------------------------------------------------------------
# Header label parsing

NUMERIC_RX = re.compile(r"^\s*(\d{1,3})\)\s+(.+?)$")
APPENDIX_RX = re.compile(
    r"^\s*([A-Z])(\d{1,3})[.\u2024\u2027\uFF0E](?:\s{0,2}(.+?))?\s*$",
    re.IGNORECASE,
)
ROMAN_RX = re.compile(
    r"^\s*((?:M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})))\.\s*(.+?)?\s*$",
    re.IGNORECASE,
)
ALPHA_RX = re.compile(r"^\s*([A-Z])\.\s*(.+?)?\s*$", re.IGNORECASE)


def _roman_to_int(value: str) -> Optional[int]:
    if not value:
        return None
    numerals = {
        "M": 1000,
        "D": 500,
        "C": 100,
        "L": 50,
        "X": 10,
        "V": 5,
        "I": 1,
    }
    total = 0
    prev = 0
    for ch in value.upper():
        if ch not in numerals:
            return None
        val = numerals[ch]
        if val > prev:
            total += val - 2 * prev
        else:
            total += val
        prev = val
    return total


@dataclass(frozen=True)
class _SeriesKey:
    kind: str
    prefix: Optional[str]


def _classify_header(label: str) -> Optional[Tuple[_SeriesKey, int]]:
    label = label or ""
    if not label:
        return None

    match = APPENDIX_RX.match(label)
    if match:
        key = _SeriesKey("APPX", match.group(1).upper())
        return key, int(match.group(2))

    match = NUMERIC_RX.match(label)
    if match:
        key = _SeriesKey("NUM", None)
        return key, int(match.group(1))

    match = ROMAN_RX.match(label)
    if match:
        number = _roman_to_int(match.group(1))
        if number is not None:
            key = _SeriesKey("ROMAN", None)
            return key, number

    match = ALPHA_RX.match(label)
    if match:
        key = _SeriesKey("ALPHA", None)
        return key, ord(match.group(1).upper()) - ord("A") + 1

    return None


# ---------------------------------------------------------------------------
# Input window representation


@dataclass
class _Window:
    page_index: int
    raw_text: str
    norm_text: str
    start_char: int
    end_char: int
    line_map: List[Tuple[int, int]]

    def slice(self, start: int, end: int) -> str:
        start = max(self.start_char, start)
        end = min(self.end_char, end)
        local_start = max(0, start - self.start_char)
        local_end = max(0, end - self.start_char)
        return self.raw_text[local_start:local_end]


def _make_windows(
    before: Mapping[str, object],
    after: Mapping[str, object],
    page_texts: Sequence[str],
    tokens_by_page: Optional[Sequence[Sequence[Mapping[str, object]]]] = None,
) -> List[_Window]:
    if not page_texts:
        return []

    before_page = max(1, int(before.get("page") or 1))
    after_page = max(1, int(after.get("page") or before_page))
    start_page = min(before_page, len(page_texts))
    end_page = min(max(after_page, start_page), len(page_texts))

    windows: List[_Window] = []
    for page in range(start_page, end_page + 1):
        text = page_texts[page - 1] if 0 <= page - 1 < len(page_texts) else ""
        norm = _normalise(text)
        tokens = tokens_by_page[page - 1] if tokens_by_page and 0 <= page - 1 < len(tokens_by_page) else []
        spans: List[Tuple[int, int]] = []
        if tokens:
            for tok in tokens:
                start = int(tok.get("char_start") or tok.get("start", 0) or 0)
                end = int(tok.get("char_end") or tok.get("end", start))
                spans.append((start, end))
        else:
            spans = [(0, len(text))]
        windows.append(
            _Window(
                page_index=page,
                raw_text=text,
                norm_text=norm,
                start_char=0,
                end_char=len(text),
                line_map=spans,
            )
        )
    return windows


# ---------------------------------------------------------------------------
# Search strategies


def _regex_candidates(window: _Window, pattern: re.Pattern[str]) -> Iterator[Tuple[int, int]]:
    search_text = _normalise_spaces(window.raw_text)
    for match in pattern.finditer(search_text):
        yield match.start(), match.end()


def _label_variants(kind: str, prefix: Optional[str], index: int) -> List[str]:
    if kind == "APPX" and prefix:
        return [f"{prefix}{index}", f"{prefix}{index}.", f"{prefix} {index}.", f"{prefix}{index} ."]
    if kind == "NUM":
        return [f"{index})", f"{index} )"]
    if kind == "ROMAN":
        numerals = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]
        numeral = numerals[index - 1] if 0 < index <= len(numerals) else None
        if numeral:
            return [f"{numeral}."]
    if kind == "ALPHA":
        letter = chr(ord("A") + index - 1)
        return [f"{letter}.", f"{letter} ."]
    return []


def _build_pattern(label_variants: Sequence[str]) -> Optional[re.Pattern[str]]:
    escaped = []
    for variant in label_variants:
        cleaned = re.escape(_normalise(variant))
        if not cleaned:
            continue
        escaped.append(cleaned + r"\s+[^\n]{3,160}")
    if not escaped:
        return None
    pattern = re.compile(r"|".join(f"({alt})" for alt in escaped), re.IGNORECASE | re.DOTALL)
    return pattern


def _verify_candidate(window: _Window, fragment: str) -> Optional[Tuple[int, int]]:
    raw_norm = _normalise_spaces(window.raw_text)
    fragment_norm = _normalise(fragment)
    pos = raw_norm.find(fragment_norm)
    if pos >= 0:
        return pos, pos + len(fragment_norm)
    pos = window.norm_text.find(fragment_norm)
    if pos >= 0:
        return pos, pos + len(fragment_norm)
    return None


def _score_repair(
    *,
    style_match: bool,
    position_ok: bool,
    strict_regex: bool,
    used_soft_unwrap: bool,
    used_ocr: bool,
) -> float:
    score = 0.2
    if style_match:
        score += 0.35
    if position_ok:
        score += 0.25
    if strict_regex:
        score += 0.20
    if used_soft_unwrap:
        score += 0.10
    if used_ocr:
        score -= 0.20
    return max(0.0, min(score, 1.0))


def _position_sane(candidate: Mapping[str, object], before: Mapping[str, object], after: Mapping[str, object]) -> bool:
    page = int(candidate.get("page") or 0)
    before_page = int(before.get("page") or 0)
    after_page = int(after.get("page") or 0)
    if before_page and page < before_page:
        return False
    if after_page and page > after_page:
        return False
    return True


def _make_repair_record(
    *,
    level: Optional[int],
    label: str,
    text: str,
    page: int,
    span: Tuple[int, int],
    verification: str,
    confidence: float,
    provenance: Mapping[str, object],
) -> Dict[str, object]:
    return {
        "level": level,
        "label": label,
        "text": text,
        "page": page,
        "span": span,
        "verification": verification,
        "confidence": round(confidence, 4),
        "provenance": dict(provenance),
    }


# ---------------------------------------------------------------------------
# Public API


def aggressive_sequence_repair(
    verified_headers: Sequence[Mapping[str, object]],
    page_texts: Sequence[str],
    tokens_by_page: Optional[Sequence[Sequence[Mapping[str, object]]]] = None,
) -> Tuple[List[Mapping[str, object]], List[Mapping[str, object]]]:
    """Return ``verified_headers`` extended with repaired numbering gaps.

    Parameters
    ----------
    verified_headers:
        The list of headers that passed local verification after the LLM header
        pass.  Each entry must include ``label`` (header numbering), ``text``,
        ``page`` and optionally ``level`` and ``span``/``char_span`` metadata.
    page_texts:
        Normalised page-level text blobs.  These are used as the search space
        when attempting to recover missing headers.
    tokens_by_page:
        Optional token metadata (line level) to assist with span calculation.

    Returns
    -------
    Tuple[List[Mapping], List[Mapping]]
        The first element is the merged header list sorted by page/span.
        The second element contains the repair records that were added.
    """

    if not verified_headers:
        return list(verified_headers), []

    grouped: Dict[_SeriesKey, List[Mapping[str, object]]] = {}
    for header in verified_headers:
        label = str(header.get("label") or header.get("section_number") or "").strip()
        classified = _classify_header(label)
        if not classified:
            continue
        series, index = classified
        grouped.setdefault(series, []).append(dict(header, _seq_index=index))

    repairs: List[Mapping[str, object]] = []

    for series_key, items in grouped.items():
        ordered = sorted(items, key=lambda h: (int(h.get("page") or 0), (h.get("span") or h.get("char_span") or (0, 0))[0]))
        observed = sorted(set(h["_seq_index"] for h in ordered))
        if not observed:
            continue

        gaps: List[int] = []
        for left, right in zip(observed, observed[1:]):
            if right - left > 1:
                gaps.extend(range(left + 1, right))

        if not gaps:
            continue

        LOGGER.debug("sequence repair: series=%s gaps=%s", series_key, gaps)

        for gap_index in gaps:
            before = max((h for h in ordered if h["_seq_index"] < gap_index), key=lambda h: h["_seq_index"], default=None)
            after = min((h for h in ordered if h["_seq_index"] > gap_index), key=lambda h: h["_seq_index"], default=None)
            if before is None or after is None:
                continue

            windows = _make_windows(before, after, page_texts, tokens_by_page)
            label_variants = _label_variants(series_key.kind, series_key.prefix, gap_index)
            pattern = _build_pattern(label_variants)
            if not windows or not pattern:
                continue

            found = False
            for window in windows:
                for start, end in _regex_candidates(window, pattern):
                    fragment = _normalise_spaces(window.raw_text[start:end]).strip()
                    newline = fragment.find("\n")
                    if newline >= 0:
                        fragment = fragment[:newline]
                    fragment = fragment.strip()
                    verified = _verify_candidate(window, fragment)
                    if not verified:
                        continue
                    # Map back to raw span by counting characters (best effort)
                    raw_fragment = fragment
                    raw_match = window.raw_text.find(raw_fragment)
                    if raw_match < 0:
                        raw_match = window.raw_text.find(fragment.replace(" ", ""))
                    if raw_match < 0:
                        raw_match = verified[0]
                    span = (raw_match, raw_match + len(raw_fragment))
                    candidate_meta = {
                        "page": window.page_index,
                        "span": span,
                    }
                    if not _position_sane(candidate_meta, before, after):
                        continue
                    label = label_variants[0].replace(" ", "") if label_variants else str(gap_index)
                    label = label if label.endswith(".") or label.endswith(")") else label + "."
                    confidence = _score_repair(
                        style_match=bool(before.get("style") or after.get("style")),
                        position_ok=True,
                        strict_regex=True,
                        used_soft_unwrap=False,
                        used_ocr=False,
                    )
                    record = _make_repair_record(
                        level=before.get("level") or after.get("level"),
                        label=label,
                        text=_normalise(fragment).split(" ", 1)[-1] if " " in _normalise(fragment) else _normalise(fragment),
                        page=window.page_index,
                        span=span,
                        verification="repair",
                        confidence=confidence,
                        provenance={
                            "series": series_key.kind,
                            "index": gap_index,
                            "neighbors": {
                                "before": before.get("label"),
                                "after": after.get("label"),
                            },
                            "search": "regex",
                        },
                    )
                    repairs.append(record)
                    found = True
                    break
                if found:
                    break
            if not found:
                LOGGER.debug("sequence repair: failed to locate %s%s", series_key.prefix or "", gap_index)

    if not repairs:
        return list(verified_headers), []

    merged = list(verified_headers) + repairs
    merged.sort(key=lambda h: (int(h.get("page") or 0), (h.get("span") or h.get("char_span") or (0, 0))[0]))
    return merged, repairs


__all__ = ["aggressive_sequence_repair"]

