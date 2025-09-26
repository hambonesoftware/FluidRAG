from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from backend.efhg.fluid import Span
from backend.uf_chunker import UFChunk

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


def _dominant_header(span: Span, chunks: Dict[str, UFChunk], headers: List[Dict[str, object]]) -> Tuple[str | None, float]:
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


def score_graph(span: Span, header_ctx: GraphContext, chunks: Dict[str, UFChunk], params: Dict[str, float] | None = None) -> Tuple[float, Dict[str, float]]:
    params = params or DEFAULT_PARAMS
    penalties = {
        "header_mismatch": 0.0,
        "domain_conflict": 0.0,
        "reference_gap": 0.0,
    }
    dominant_label, overlap = _dominant_header(span, chunks, header_ctx.headers)
    header_score = params["wH"] * (1.0 if dominant_label else 0.0)
    domain_score = params["wD"] * (1.0 if overlap > 0 else 0.5)
    param_support = any(chunks[cid].lex.get("numbers") for cid in span.chunk_ids)
    param_score = params["wP"] * (1.0 if param_support else 0.4)
    ref_score = params["wR"] * (1.0 if header_ctx.references else 0.5)
    table_score = params["wC"] * (1.0 if header_ctx.tables else 0.4)
    penalties["header_mismatch"] = 0.0 if dominant_label else 0.6
    score = header_score + domain_score + param_score + ref_score + table_score - sum(penalties.values())
    return score, penalties


def snap_and_trim(span: Span, header_ctx: GraphContext, chunks: Dict[str, UFChunk]) -> Span:
    dominant_label, _ = _dominant_header(span, chunks, header_ctx.headers)
    if not dominant_label:
        return span
    header_spans = [h for h in header_ctx.headers if h.get("label") == dominant_label]
    if not header_spans:
        return span
    header_span = header_spans[0]
    h_start, h_end = header_span.get("span", span.span)
    s_start, s_end = span.span
    new_start = max(h_start, s_start)
    new_end = min(h_end + 400, s_end)
    return Span(chunk_ids=span.chunk_ids, text=span.text, page=span.page, span=(new_start, new_end), flow_total=span.flow_total)


__all__ = ["GraphContext", "score_graph", "snap_and_trim", "DEFAULT_PARAMS"]
