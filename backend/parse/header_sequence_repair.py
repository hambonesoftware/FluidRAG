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


def _normalise_with_map(text: str) -> Tuple[str, List[int]]:
    """Return a normalised string alongside a map back to raw offsets."""

    cleaned: List[str] = []
    mapping: List[int] = []
    last_space = False
    for idx, char in enumerate(text or ""):
        if char in _ZERO_WIDTH:
            continue
        if char in _SPACE_VARIANTS or char in "\r\n\t":
            if last_space:
                continue
            cleaned.append(" ")
            mapping.append(idx)
            last_space = True
            continue
        last_space = False
        if char in _DOT_VARIANTS:
            cleaned.append(".")
        else:
            cleaned.append(char)
        mapping.append(idx)
    return "".join(cleaned), mapping


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


def _int_to_roman(number: int) -> Optional[str]:
    if number <= 0:
        return None
    mapping = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    result: List[str] = []
    remainder = number
    for value, numeral in mapping:
        while remainder >= value:
            remainder -= value
            result.append(numeral)
        if remainder == 0:
            break
    return "".join(result) if result else None


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
    search_text: str
    search_map: List[int]
    base_offset: int
    lines: List[str]
    line_spans: List[Tuple[int, int]]

    def absolute_span(self, local_span: Tuple[int, int]) -> Tuple[int, int]:
        return self.base_offset + local_span[0], self.base_offset + local_span[1]


def _page_line_data(text: str) -> Tuple[List[str], List[Tuple[int, int]]]:
    lines: List[str] = []
    spans: List[Tuple[int, int]] = []
    cursor = 0
    for raw_line in text.splitlines(True):
        start = cursor
        cursor += len(raw_line)
        line = raw_line.rstrip("\r\n")
        lines.append(line)
        spans.append((start, cursor))
    if not lines and text:
        lines = [text]
        spans = [(0, len(text))]
    return lines, spans


def _line_index_from_header(header: Mapping[str, object], spans: Sequence[Tuple[int, int]]) -> Optional[int]:
    if not spans:
        return None
    if "line_idx" in header and header.get("line_idx") is not None:
        try:
            idx = int(header.get("line_idx"))
        except Exception:
            idx = None
        if idx is not None:
            return max(0, min(idx, len(spans) - 1))
    span = header.get("span") or header.get("char_span")
    if isinstance(span, (list, tuple)) and len(span) >= 2:
        start_char = int(span[0])
        for idx, (start, end) in enumerate(spans):
            if start <= start_char < end:
                return idx
        return len(spans) - 1
    return None


def _clip_line_range(lo: int, hi: int, total: int) -> Tuple[int, int]:
    if total <= 0:
        return 0, 0
    lo = max(0, min(lo, total))
    hi = max(lo, min(hi, total))
    return lo, hi


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
    before_page = min(before_page, len(page_texts))
    after_page = min(after_page, len(page_texts))

    windows: List[_Window] = []

    for page in range(before_page, after_page + 1):
        page_text = page_texts[page - 1] if 0 <= page - 1 < len(page_texts) else ""
        lines, spans = _page_line_data(page_text)
        total_lines = len(lines)

        if page == before_page:
            before_idx = _line_index_from_header(before, spans) or 0
            start_line = min(before_idx + 1, total_lines)
            end_line = total_lines if page != after_page else (_line_index_from_header(after, spans) or total_lines)
            if page == after_page:
                end_line = max(start_line, end_line)
            lo = max(0, start_line - 2)
            hi = min(total_lines, (start_line + 10) if page != after_page else end_line + 2)
        elif page == after_page:
            after_idx = _line_index_from_header(after, spans) or total_lines
            lo = max(0, after_idx - 10)
            hi = min(total_lines, after_idx + 2)
        else:
            lo, hi = 0, total_lines

        lo, hi = _clip_line_range(lo, hi, total_lines)
        if hi <= lo:
            continue

        start_char = spans[lo][0] if spans else 0
        end_char = spans[hi - 1][1] if spans else len(page_text)
        raw_window = page_text[start_char:end_char]
        search_text, search_map = _normalise_with_map(raw_window)
        norm_text = _normalise(raw_window)

        window_lines = lines[lo:hi] if lines else []
        line_spans: List[Tuple[int, int]] = []
        for idx in range(lo, hi):
            segment = spans[idx]
            local_start = max(0, segment[0] - start_char)
            local_end = max(0, segment[1] - start_char)
            line_spans.append((local_start, local_end))

        windows.append(
            _Window(
                page_index=page,
                raw_text=raw_window,
                norm_text=norm_text,
                search_text=search_text,
                search_map=search_map,
                base_offset=start_char,
                lines=window_lines,
                line_spans=line_spans,
            )
        )

    return windows


# ---------------------------------------------------------------------------
# Search strategies


@dataclass
class _SearchResult:
    fragment: str
    span: Tuple[int, int]
    strict_regex: bool
    used_soft_unwrap: bool
    used_ocr: bool
    search: str


def _regex_candidates(window: _Window, pattern: re.Pattern[str]) -> Iterator[Tuple[int, int]]:
    search_text = window.search_text
    for match in pattern.finditer(search_text):
        yield match.start(), match.end()


def _match_to_result(
    window: _Window,
    span: Tuple[int, int],
    *,
    search: str,
    strict: bool,
    used_soft: bool = False,
    used_ocr: bool = False,
) -> Optional[_SearchResult]:
    start, end = span
    if end <= start:
        return None
    if window.search_map:
        start_idx = max(0, min(start, len(window.search_map) - 1))
        end_idx = max(0, min(end - 1, len(window.search_map) - 1))
        raw_start = window.search_map[start_idx]
        raw_end = window.search_map[end_idx] + 1
    else:
        raw_start = max(0, min(start, len(window.raw_text)))
        raw_end = max(raw_start + 1, min(end, len(window.raw_text)))
    if raw_end <= raw_start:
        return None
    fragment = window.raw_text[raw_start:raw_end].strip()
    if not fragment:
        return None
    return _SearchResult(
        fragment=fragment,
        span=window.absolute_span((raw_start, raw_end)),
        strict_regex=strict,
        used_soft_unwrap=used_soft,
        used_ocr=used_ocr,
        search=search,
    )


def _raw_span_to_search_span(window: _Window, raw_span: Tuple[int, int]) -> Tuple[int, int]:
    raw_start, raw_end = raw_span
    if not window.search_map:
        return raw_start, raw_end
    start_idx = 0
    for idx, value in enumerate(window.search_map):
        if value >= raw_start:
            start_idx = idx
            break
    else:
        start_idx = len(window.search_map) - 1
    end_idx = start_idx
    for idx in range(start_idx, len(window.search_map)):
        if window.search_map[idx] >= raw_end:
            end_idx = idx
            break
    else:
        end_idx = len(window.search_map)
    if end_idx <= start_idx:
        end_idx = min(len(window.search_map), start_idx + 1)
    return start_idx, end_idx


def _label_variants(kind: str, prefix: Optional[str], index: int) -> List[str]:
    if kind == "APPX" and prefix:
        return [f"{prefix}{index}.", f"{prefix}{index}", f"{prefix} {index}.", f"{prefix}{index} ."]
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


def _render_label(series: _SeriesKey, index: int) -> str:
    if series.kind == "APPX" and series.prefix:
        return f"{series.prefix}{index}."
    if series.kind == "NUM":
        return f"{index})"
    if series.kind == "ROMAN":
        numeral = _int_to_roman(index) or str(index)
        return f"{numeral}."
    if series.kind == "ALPHA":
        letter = chr(ord("A") + index - 1)
        return f"{letter}."
    return str(index)


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


def _regex_probe(
    window: _Window,
    pattern: Optional[re.Pattern[str]],
    label_variants: Sequence[str],
) -> Optional[_SearchResult]:
    if pattern is None:
        return None
    for span in _regex_candidates(window, pattern):
        result = _match_to_result(window, span, search="regex", strict=True)
        if not result:
            continue
        lines = result.fragment.splitlines() or [result.fragment]
        first_line = lines[0]
        if not _extract_header_text(first_line, label_variants):
            continue
        text = _extract_header_text(result.fragment, label_variants)
        if not text:
            continue
        return result
    return None


def _header_first_segmentation_probe(
    window: _Window, label_variants: Sequence[str]
) -> Optional[_SearchResult]:
    if not window.lines:
        return None
    targets = [_normalise(variant) for variant in label_variants]
    for line, raw_span in zip(window.lines, window.line_spans):
        normalised_line = _normalise(line)
        if any(normalised_line.startswith(target) for target in targets):
            search_span = _raw_span_to_search_span(window, raw_span)
            result = _match_to_result(window, search_span, search="header_seg", strict=True)
            if result:
                return result
    return None


def _soft_unwrap_probe(window: _Window, label_variants: Sequence[str]) -> Optional[_SearchResult]:
    if not window.lines:
        return None
    targets = [_normalise(variant) for variant in label_variants]
    for idx, (line, raw_span) in enumerate(zip(window.lines, window.line_spans)):
        normalised_line = _normalise(line)
        matched = next((target for target in targets if normalised_line.startswith(target)), None)
        if not matched:
            continue
        remainder = normalised_line[len(matched) :].strip()
        if remainder and len(remainder.split()) > 6:
            continue
        if idx + 1 >= len(window.line_spans):
            continue
        combined_span = (raw_span[0], window.line_spans[idx + 1][1])
        search_span = _raw_span_to_search_span(window, combined_span)
        result = _match_to_result(
            window,
            search_span,
            search="soft_unwrap",
            strict=True,
            used_soft=True,
        )
        if result:
            return result
    return None


def _ocr_rescan_probe(
    window: _Window, label_variants: Sequence[str]
) -> Optional[_SearchResult]:
    if not window.search_text:
        return None
    lowered = window.search_text.lower()
    for variant in label_variants:
        key = _normalise(variant).lower()
        if not key:
            continue
        idx = lowered.find(key)
        if idx < 0:
            continue
        end = min(len(window.search_text), idx + len(key) + 160)
        result = _match_to_result(
            window,
            (idx, end),
            search="ocr_rescan",
            strict=False,
            used_ocr=True,
        )
        if result:
            return result
    return None


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


def _extract_header_text(fragment: str, label_variants: Sequence[str]) -> str:
    cleaned = fragment.replace("\r", "").strip()
    if not cleaned:
        return ""
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    if not lines:
        lines = [cleaned]

    remainder = ""
    first_line = lines[0]
    matched_variant = False
    for variant in label_variants:
        pattern = re.compile(rf"^\s*{re.escape(variant.strip())}\s*(.+)$", re.IGNORECASE)
        match = pattern.match(first_line)
        if match:
            candidate = match.group(1).strip()
            if candidate and candidate not in {".", "-", ":"}:
                matched_variant = True
                remainder = candidate
                break
            # Try the next variant to avoid capturing stray punctuation
            continue
    if not matched_variant:
        parts = _collapse_whitespace(first_line).split(" ", 1)
        remainder = parts[1] if len(parts) == 2 else ""

    extra_parts: List[str] = []
    for line in lines[1:]:
        token = line.split(" ", 1)[0]
        if _classify_header(token):
            break
        extra_parts.append(line)

    pieces = []
    if remainder:
        pieces.append(remainder)
    pieces.extend(extra_parts)
    return _collapse_whitespace(" ".join(pieces)).strip()


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
            before = max(
                (h for h in ordered if h["_seq_index"] < gap_index),
                key=lambda h: h["_seq_index"],
                default=None,
            )
            after = min(
                (h for h in ordered if h["_seq_index"] > gap_index),
                key=lambda h: h["_seq_index"],
                default=None,
            )
            if before is None or after is None:
                continue

            windows = _make_windows(before, after, page_texts, tokens_by_page)
            label_variants = _label_variants(series_key.kind, series_key.prefix, gap_index)
            pattern = _build_pattern(label_variants)
            if not windows or not label_variants:
                continue

            candidate_result: Optional[_SearchResult] = None
            chosen_window: Optional[_Window] = None
            header_text: str = ""
            for window in windows:
                for probe in (
                    lambda: _regex_probe(window, pattern, label_variants),
                    lambda: _header_first_segmentation_probe(window, label_variants),
                    lambda: _soft_unwrap_probe(window, label_variants),
                    lambda: _ocr_rescan_probe(window, label_variants),
                ):
                    candidate = probe()
                    if not candidate:
                        continue
                    if not _verify_candidate(window, candidate.fragment):
                        continue
                    meta = {"page": window.page_index, "span": candidate.span}
                    if not _position_sane(meta, before, after):
                        continue
                    text = _extract_header_text(candidate.fragment, label_variants).strip()
                    if not text:
                        continue
                    candidate_result = candidate
                    chosen_window = window
                    header_text = text
                    break
                if candidate_result:
                    break

            if not candidate_result or not chosen_window or not header_text:
                LOGGER.debug("sequence repair: failed to locate %s%s", series_key.prefix or "", gap_index)
                continue

            header_label = _render_label(series_key, gap_index)
            if _normalise(header_text).lower() == _normalise(header_label).lower():
                LOGGER.debug(
                    "sequence repair: candidate text empty for %s%s", series_key.prefix or "", gap_index
                )
                continue

            confidence = _score_repair(
                style_match=bool(before.get("style") or after.get("style")),
                position_ok=True,
                strict_regex=candidate_result.strict_regex,
                used_soft_unwrap=candidate_result.used_soft_unwrap,
                used_ocr=candidate_result.used_ocr,
            )

            provenance = {
                "series": series_key.kind,
                "index": gap_index,
                "neighbors": {"before": before.get("label"), "after": after.get("label")},
                "search": candidate_result.search,
            }

            record = _make_repair_record(
                level=before.get("level") or after.get("level"),
                label=header_label,
                text=header_text,
                page=chosen_window.page_index,
                span=candidate_result.span,
                verification="repair",
                confidence=confidence,
                provenance=provenance,
            )
            repairs.append(record)

    if not repairs:
        return list(verified_headers), []

    merged = list(verified_headers) + repairs
    merged.sort(key=lambda h: (int(h.get("page") or 0), (h.get("span") or h.get("char_span") or (0, 0))[0]))
    return merged, repairs


__all__ = ["aggressive_sequence_repair"]

