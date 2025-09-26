"""Token-aware microchunking utilities used by the FluidRAG pipeline."""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
    TypedDict,
)

import regex as re

# Default chunk configuration (matches the prompt instructions)
DEFAULT_CHUNK_SIZE = 90
DEFAULT_OVERLAP = 12
BOUNDARY_WINDOW = 24


class MicroChunk(TypedDict, total=False):
    """Structured metadata emitted for every UF-chunk."""

    doc_id: str
    micro_id: str
    text: str
    norm_text: str
    token_count: int
    token_span: Tuple[int, int]
    page: Optional[int]
    pages: List[int]
    char_span: Optional[Tuple[int, int]]
    char_count: int
    line_count: int
    part_span: Optional[Tuple[int, int]]
    part_indices: List[int]
    para_id: Optional[str]
    header_anchor: Optional[str]
    section_id: Optional[str]
    section_title: Optional[str]
    sequence_index: int
    style: Dict[str, object]
    lex: Dict[str, object]
    emb: List[float]
    domain_hint: Optional[str]
    meta: Dict[str, object]


@dataclass
class _Token:
    """Internal representation of a token with offsets and source mapping."""

    text: str
    start: int
    end: int
    part_index: int


_TOKEN_PATTERN = re.compile(r"\p{L}[\p{L}\p{Mn}\p{Mc}\p{Pd}\p{Pc}\p{Nd}]*|\p{N}+|[^\s]", re.UNICODE)
_SENTENCE_END_RE = re.compile(r"""[.!?]+['")]{0,1}\s*$""")
_BULLET_RE = re.compile(r"^\s*(?:[-*\u2022\u2023\u2043]|\d+\.|\d+\))\s+")
_WHITESPACE_RE = re.compile(r"\s+")
_DEHYPHEN_RE = re.compile(r"(?<=\w)[-\u2010\u2011\u2012\u2013\u2014\u2212]\n(?=\w)")
_HEADER_MARK_RE = re.compile(r"^\s*(?:\d+\)|[A-Z]\d+\.)")
_MODAL_TERMS = {"shall", "must", "should", "will"}
_CITATION_RX = re.compile(r"\b(?:NFPA|ISO|IEC|EN|API|ASTM|\u00a7)\b")
_UNIT_RX = re.compile(r"\b(?:mm|cm|m|km|in|ft|°c|°f|psi|kpa|bar|hz|rpm|kw|mw|s|ms)\b", re.IGNORECASE)
_NUMBER_RX = re.compile(r"\b\d+(?:[.,]\d+)?(?:\s*[×x]\s*10\^\d+)?\b")


def _normalize_text(text: str) -> str:
    """Return a normalised representation used for hashing and retrieval."""

    if not text:
        return ""
    cleaned = _DEHYPHEN_RE.sub("", text)
    cleaned = cleaned.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    cleaned = cleaned.replace("\xa0", " ")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def _tokenize(text: str) -> Iterable[re.Match[str]]:
    return _TOKEN_PATTERN.finditer(text)


def _build_tokens(parts: Sequence[Mapping[str, Any]]) -> Tuple[str, List[_Token], List[Tuple[int, int, int]]]:
    """Return the combined document text, tokens, and part spans."""

    fragments: List[str] = []
    offsets: List[Tuple[int, int, int]] = []
    running = 0
    for idx, part in enumerate(parts):
        fragment = str(part.get("text") or "")
        fragments.append(fragment)
        start = running
        running += len(fragment)
        offsets.append((start, running, idx))
        if idx + 1 < len(parts):
            fragments.append("\n")
            running += 1
    doc_text = "".join(fragments)

    tokens: List[_Token] = []
    part_pointer = 0
    part_bounds = list(offsets)
    for match in _tokenize(doc_text):
        start, end = match.span()
        while (
            part_pointer + 1 < len(part_bounds)
            and start >= part_bounds[part_pointer][1]
        ):
            part_pointer += 1
        tokens.append(
            _Token(
                text=match.group(0),
                start=start,
                end=end,
                part_index=part_bounds[part_pointer][2] if part_bounds else 0,
            )
        )
    return doc_text, tokens, offsets


def _candidate_boundaries(doc_text: str, tokens: Sequence[_Token], offsets: Sequence[Tuple[int, int, int]]) -> List[int]:
    """Return token indices that represent soft boundaries."""

    boundaries = {0, len(tokens)}
    for idx in range(1, len(tokens)):
        prev_token = tokens[idx - 1]
        gap = doc_text[prev_token.end : tokens[idx].start]
        if not gap:
            continue
        if "\n" in gap and gap.count("\n") >= 2:
            boundaries.add(idx)
            continue
        if _BULLET_RE.match(gap.lstrip()):
            boundaries.add(idx)
            continue
        prev_text = doc_text[: prev_token.end]
        if _SENTENCE_END_RE.search(prev_text[-8:]):
            boundaries.add(idx)
            continue
        # Header markers at the start of the next line
        line_start = doc_text.rfind("\n", 0, tokens[idx].start) + 1
        line = doc_text[line_start : tokens[idx].start]
        if _HEADER_MARK_RE.match(line.strip()):
            boundaries.add(idx)
            continue
        # Part boundary alignment
        for start, end, part_idx in offsets:
            if prev_token.end <= end <= tokens[idx].start:
                boundaries.add(idx)
                break
    return sorted(boundaries)


def _choose_boundary(target: int, candidates: Sequence[int], lower: int, upper: int) -> int:
    """Select the best boundary near the ``target`` token index."""

    if target >= upper:
        return upper
    window_low = max(lower + 1, target - BOUNDARY_WINDOW)
    window_high = min(upper, target + BOUNDARY_WINDOW)
    best = None
    best_gap = None
    candidate_set = set(candidates)
    for idx in range(window_low, window_high + 1):
        if idx not in candidate_set:
            continue
        gap = abs(idx - target)
        if best is None or gap < best_gap:
            best = idx
            best_gap = gap
    if best is None:
        # Fallback to the next available boundary after the target
        for idx in candidates:
            if idx > target:
                return idx
        return upper
    return min(max(best, lower + 1), upper)


def _select_metadata(parts: Sequence[Mapping[str, Any]], indices: Sequence[int], key: str) -> Optional[str]:
    values: List[str] = []
    for idx in indices:
        value = parts[idx].get(key)
        if value:
            values.append(str(value))
    if not values:
        return None
    # Prefer the most frequent non-empty value, falling back to the first
    counts: Dict[str, int] = {}
    first_seen: Dict[str, int] = {}
    for idx, value in enumerate(values):
        counts[value] = counts.get(value, 0) + 1
        first_seen.setdefault(value, idx)
    ordered = sorted(values, key=lambda item: (-counts[item], first_seen[item]))
    return ordered[0]


def _extract_style(parts: Sequence[Mapping[str, Any]], indices: Sequence[int]) -> Dict[str, object]:
    if not indices:
        return {}
    fonts: List[float] = []
    bold_votes = 0
    indents: List[float] = []
    for idx in indices:
        part = parts[idx]
        font = part.get("font_size")
        if isinstance(font, (int, float)):
            fonts.append(float(font))
        if part.get("bold") or part.get("font_weight") == "bold":
            bold_votes += 1
        indent = part.get("indent") or part.get("left")
        try:
            if indent is not None:
                indents.append(float(indent))
        except Exception:
            continue
    style: Dict[str, object] = {}
    if fonts:
        fonts.sort()
        mid = len(fonts) // 2
        style["font_size"] = fonts[mid]
    if indents:
        indents.sort()
        style["indent"] = indents[0]
    style["bold"] = bold_votes >= max(1, len(indices) // 2)
    return style


def _extract_lex(text: str) -> Dict[str, object]:
    normalized = _normalize_text(text)
    tokens = {token.lower() for token in normalized.split()}
    modal_flags = sorted(term for term in _MODAL_TERMS if term in tokens)
    numbers = sorted({match.group(0) for match in _NUMBER_RX.finditer(normalized)})
    units = sorted({match.group(0).lower() for match in _UNIT_RX.finditer(normalized)})
    citations = bool(_CITATION_RX.search(normalized))
    return {
        "modal_flags": modal_flags,
        "numbers": numbers,
        "units": units,
        "citation_hint": citations,
    }


def _compute_embedding(text: str, dims: int = 8) -> List[float]:
    if not text:
        return [0.0] * dims
    digest = hashlib.sha1(text.encode("utf-8")).digest()
    vector: List[float] = []
    for idx in range(dims):
        raw = digest[idx]
        vector.append(round((raw / 255.0) * 2.0 - 1.0, 6))
    return vector


def _infer_domain_hint(text: str) -> Optional[str]:
    lowered = text.lower()
    if any(term in lowered for term in ("safety", "lockout", "ppe")):
        return "safety"
    if any(term in lowered for term in ("performance", "efficiency", "load", "torque")):
        return "performance"
    if any(term in lowered for term in ("quality", "inspection", "audit")):
        return "quality"
    return None


def _microchunk_from_window(
    *,
    doc_id: str,
    doc_text: str,
    parts: Sequence[Mapping[str, Any]],
    tokens: Sequence[_Token],
    token_indices: Tuple[int, int],
) -> MicroChunk:
    start_idx, end_idx = token_indices
    window_tokens = tokens[start_idx:end_idx]
    if not window_tokens:
        raise ValueError("microchunk windows must contain at least one token")

    start_char = window_tokens[0].start
    end_char = window_tokens[-1].end
    raw_text = doc_text[start_char:end_char]
    norm_text = _normalize_text(raw_text)
    micro_id = "uf-" + hashlib.sha1(norm_text.encode("utf-8")).hexdigest()[:12]

    part_indices = sorted({token.part_index for token in window_tokens})
    part_span: Optional[Tuple[int, int]] = None
    if part_indices:
        part_span = (part_indices[0], part_indices[-1])

    page_candidates: Set[int] = set()
    page = None
    for idx in part_indices:
        part = parts[idx]
        for key in ("page", "page_start", "page_end"):
            value = part.get(key)
            if value is None:
                continue
            try:
                page_num = int(value)
            except (TypeError, ValueError):
                continue
            page_candidates.add(page_num)
    if page_candidates:
        page = min(page_candidates)

    para_id = _select_metadata(parts, part_indices, "chunk_id") or _select_metadata(
        parts, part_indices, "para_id"
    )

    char_count = len(raw_text)
    line_count = raw_text.count("\n") + 1 if raw_text else 0
    pages = sorted(page_candidates)

    chunk: MicroChunk = {
        "doc_id": doc_id,
        "micro_id": micro_id,
        "text": raw_text.strip(),
        "norm_text": norm_text,
        "token_count": end_idx - start_idx,
        "token_span": (start_idx, end_idx),
        "page": page,
        "pages": pages,
        "char_span": (start_char, end_char),
        "char_count": char_count,
        "line_count": line_count,
        "part_span": part_span,
        "part_indices": part_indices,
        "para_id": para_id,
        "header_anchor": _select_metadata(parts, part_indices, "header_anchor"),
        "section_id": _select_metadata(parts, part_indices, "section_id"),
        "section_title": _select_metadata(parts, part_indices, "section_title"),
    }
    chunk["style"] = _extract_style(parts, part_indices)
    chunk["lex"] = _extract_lex(raw_text)
    chunk["emb"] = _compute_embedding(norm_text)
    chunk["domain_hint"] = _infer_domain_hint(norm_text)

    line_meta_entries: List[Dict[str, object]] = []
    blank_scores: List[int] = []
    para_flags: List[bool] = []
    prev_puncts: List[object] = []
    list_contexts: List[str] = []
    for idx in part_indices:
        part = parts[idx]
        style_jump_raw = part.get("style_jump") or {}
        style_jump = {
            "font_delta": float(style_jump_raw.get("font_delta") or 0.0),
            "bold_flip": bool(style_jump_raw.get("bold_flip")),
            "left_x_delta": float(style_jump_raw.get("left_x_delta") or 0.0),
        }
        virtual_blank = int(part.get("virtual_blank_lines_before") or 0)
        para_flag = bool(part.get("para_start"))
        prev_punct = part.get("prev_trailing_punct")
        list_ctx = str(part.get("list_context") or "none")
        y_gap = float(part.get("y_gap") or 0.0)
        line_height = float(part.get("line_height") or 0.0)
        newline_count = int(part.get("newline_count") or 0)
        left_x_val = part.get("left_x")
        try:
            left_x = float(left_x_val) if left_x_val is not None else None
        except Exception:
            left_x = None
        font_pt_val = part.get("font_pt", part.get("font_size"))
        try:
            font_pt = float(font_pt_val) if font_pt_val is not None else 0.0
        except Exception:
            font_pt = 0.0
        line_meta_entries.append(
            {
                "text": part.get("text"),
                "page": part.get("page"),
                "line_idx": part.get("line_idx"),
                "is_blank": bool(part.get("is_blank")),
                "newline_count": newline_count,
                "y_gap": y_gap,
                "line_height": line_height,
                "virtual_blank_lines_before": virtual_blank,
                "style_jump": style_jump,
                "para_start": para_flag,
                "prev_trailing_punct": prev_punct,
                "list_context": list_ctx,
                "left_x": left_x,
                "font_pt": font_pt,
                "bold": bool(part.get("bold")),
            }
        )
        blank_scores.append(virtual_blank)
        para_flags.append(para_flag)
        prev_puncts.append(prev_punct)
        list_contexts.append(list_ctx)

    meta: Dict[str, object] = dict(chunk.get("meta") or {})
    meta["blank_lines_before"] = int(max(blank_scores) if blank_scores else 0)
    meta["para_start"] = any(para_flags)
    meta["prev_trailing_punct"] = _majority_vote(prev_puncts, default=None, skip={None, ""})
    meta["list_context"] = _majority_vote(list_contexts, default="none", skip={None, ""})
    meta["line_metas"] = line_meta_entries
    meta["line_part_indices"] = list(part_indices)
    chunk["meta"] = meta
    return chunk


def microchunk_text(
    parts: Sequence[Mapping[str, Any]],
    *,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    boundary_align: bool = True,
) -> List[MicroChunk]:
    """Microchunk source ``parts`` into overlapping token windows.

    Parameters
    ----------
    parts:
        Sequence of ordered document segments.  Each part must provide a ``text``
        field and may include optional metadata such as ``doc_id`` or ``section``
        information.  The function treats the provided order as canonical.
    size:
        Target number of tokens per microchunk.
    overlap:
        Number of tokens to retain between adjacent windows.
    boundary_align:
        When ``True`` the splitter nudges window ends towards natural sentence or
        bullet boundaries within ±32 tokens of the target size.
    """

    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if not parts:
        return []

    doc_id = str(parts[0].get("doc_id") or parts[0].get("document_id") or parts[0].get("source") or "doc-unknown")
    doc_text, tokens, offsets = _build_tokens(parts)
    if not tokens:
        return []

    boundaries = _candidate_boundaries(doc_text, tokens, offsets) if boundary_align else list(range(len(tokens) + 1))

    microchunks: List[MicroChunk] = []
    total_tokens = len(tokens)
    start_idx = 0
    step = max(1, size - overlap)

    while start_idx < total_tokens:
        target_end = start_idx + size
        upper_bound = total_tokens
        if boundary_align:
            end_idx = _choose_boundary(target_end, boundaries, start_idx, upper_bound)
        else:
            end_idx = min(target_end, total_tokens)
        if end_idx <= start_idx:
            end_idx = min(start_idx + size, total_tokens)
            if end_idx <= start_idx:
                end_idx = min(start_idx + 1, total_tokens)
        chunk = _microchunk_from_window(
            doc_id=doc_id,
            doc_text=doc_text,
            parts=parts,
            tokens=tokens,
            token_indices=(start_idx, end_idx),
        )
        chunk["sequence_index"] = len(microchunks)
        microchunks.append(chunk)
        if end_idx >= total_tokens:
            break
        next_start = end_idx - overlap
        if next_start <= start_idx:
            next_start = start_idx + step
        start_idx = max(0, next_start)
    return microchunks


__all__ = ["MicroChunk", "microchunk_text"]
def _majority_vote(values: Sequence[object], default: object | None = None, *, skip: Optional[Sequence[object]] = None) -> object | None:
    skip_set = set(skip or [])
    filtered = [value for value in values if value not in skip_set]
    if not filtered:
        return default
    counts = Counter(filtered)
    best = max(counts.values()) if counts else 0
    winners = {value for value, count in counts.items() if count == best}
    for value in filtered:
        if value in winners:
            return value
    return filtered[0] if filtered else default
