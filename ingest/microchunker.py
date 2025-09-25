"""Token-aware microchunking utilities used by the FluidRAG pipeline."""
from __future__ import annotations

import hashlib
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
DEFAULT_CHUNK_SIZE = 386
DEFAULT_OVERLAP = 96
BOUNDARY_WINDOW = 32


class MicroChunk(TypedDict, total=False):
    """Structured metadata emitted for every microchunk."""

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
    micro_id = hashlib.sha1(norm_text.encode("utf-8")).hexdigest()[:10]

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
