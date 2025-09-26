from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from backend.efhg.fluid import Span, span_from_chunk_ids
from backend.uf_chunker import HEADER_PATTERN, UFChunk

DEFAULT_PARAMS = {
    "wH": 1.0,
    "wD": 0.8,
    "wP": 0.7,
    "wR": 0.4,
    "wC": 0.8,
    "theta_final": 2.5,
}


@dataclass
class GraphContext:
    headers: List[Dict[str, object]]
    references: List[Dict[str, object]]
    tables: List[Dict[str, object]]
    domain: str | None = None


def _dominant_header(span: Span, chunks: Dict[str, UFChunk], headers: Sequence[Dict[str, object]]) -> Tuple[str | None, float]:
    if not headers:
        return None, 0.0
    best = None
    best_overlap = -1
    for header in headers:
        if header.get("page") != span.page:
            continue
        h_start, h_end = header.get("span", (0, 0))
        s_start, s_end = span.span
        overlap = max(0, min(h_end, s_end) - max(h_start, s_start))
        if overlap > best_overlap:
            best = header
            best_overlap = overlap
    if best is None:
        return None, 0.0
    return best.get("label"), best_overlap


def _collect_domain_hints(span: Span, chunks: Dict[str, UFChunk]) -> List[str]:
    hints: List[str] = []
    for cid in span.chunk_ids:
        hint = chunks[cid].domain_hint
        if hint:
            hints.append(hint)
    return hints


def _chunk_has_citation(chunk: UFChunk) -> bool:
    return bool(chunk.lex.get("citation_hints"))


def _chunk_has_params(chunk: UFChunk) -> bool:
    return bool(chunk.lex.get("numbers")) or bool(chunk.lex.get("units"))


def score_graph(span: Span, header_ctx: GraphContext, chunks: Dict[str, UFChunk], params: Dict[str, float] | None = None) -> Tuple[float, Dict[str, float]]:
    params = params or DEFAULT_PARAMS
    penalties = {
        "header_mismatch": 0.0,
        "domain_conflict": 0.0,
        "reference_gap": 0.0,
        "cross_bleed": 0.0,
    }

    dominant_label, overlap = _dominant_header(span, chunks, header_ctx.headers)
    header_alignment = 1.0 if dominant_label else 0.0
    same_section = 1.0 if overlap > 0 else 0.3
    citations = 1.0 if any(_chunk_has_citation(chunks[cid]) for cid in span.chunk_ids) else 0.0
    parameters = 1.0 if any(_chunk_has_params(chunks[cid]) for cid in span.chunk_ids) else 0.0
    context_tables = 1.0 if header_ctx.tables else 0.0

    penalties["header_mismatch"] = 0.0 if dominant_label else 0.6

    domain_hints = _collect_domain_hints(span, chunks)
    if header_ctx.domain and domain_hints and header_ctx.domain not in domain_hints:
        penalties["domain_conflict"] = 0.5

    if any(
        HEADER_PATTERN.match(chunks[cid].text.strip().splitlines()[0]) and cid != span.chunk_ids[0]
        for cid in span.chunk_ids[1:]
    ):
        penalties["cross_bleed"] = 0.4

    if header_ctx.references and citations == 0.0:
        penalties["reference_gap"] = 0.3

    score = (
        params["wH"] * header_alignment
        + params["wD"] * same_section
        + params["wP"] * parameters
        + params["wR"] * citations
        + params["wC"] * context_tables
        - sum(penalties.values())
    )
    return score, penalties


def snap_and_trim(span: Span, header_ctx: GraphContext, chunks: Dict[str, UFChunk]) -> Span:
    dominant_label, _ = _dominant_header(span, chunks, header_ctx.headers)
    chunk_ids = list(span.chunk_ids)
    if dominant_label:
        for idx, cid in enumerate(chunk_ids[1:], start=1):
            chunk = chunks[cid]
            first_line = chunk.text.strip().splitlines()[0] if chunk.text.strip() else ""
            if HEADER_PATTERN.match(first_line):
                chunk_ids = chunk_ids[:idx]
                break
        header_spans = [h for h in header_ctx.headers if h.get("label") == dominant_label]
        if header_spans:
            header_span = header_spans[0]
            h_start, h_end = header_span.get("span", span.span)
            base_span = span_from_chunk_ids(chunks, chunk_ids)
            new_start = max(h_start, base_span.span[0])
            new_end = min(h_end + 400, base_span.span[1])
            trimmed = span_from_chunk_ids(chunks, chunk_ids)
            domain_hints = _collect_domain_hints(trimmed, chunks)
            if header_ctx.domain and domain_hints and header_ctx.domain not in domain_hints:
                return Span(
                    chunk_ids=[trimmed.chunk_ids[0]],
                    text=chunks[trimmed.chunk_ids[0]].text,
                    page=trimmed.page,
                    span=(chunks[trimmed.chunk_ids[0]].span_char[0], chunks[trimmed.chunk_ids[0]].span_char[1]),
                    flow_total=span.flow_total,
                )
            return Span(
                chunk_ids=trimmed.chunk_ids,
                text=trimmed.text,
                page=trimmed.page,
                span=(new_start, new_end),
                flow_total=span.flow_total,
            )

    recomputed = span_from_chunk_ids(chunks, chunk_ids)
    return Span(
        chunk_ids=recomputed.chunk_ids,
        text=recomputed.text,
        page=recomputed.page,
        span=recomputed.span,
        flow_total=span.flow_total,
    )


__all__ = ["GraphContext", "score_graph", "snap_and_trim", "DEFAULT_PARAMS"]
