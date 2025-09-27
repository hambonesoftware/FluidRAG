from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence, Tuple

from backend.headers import config as cfg
from backend.rag.embeddings import cosine
from backend.uf_chunker import UFChunk

DEFAULT_PARAMS = {
    "alpha": 0.8,
    "beta": 0.4,
    "gamma": 0.5,
    "delta": 0.3,
    "lambda": 0.2,
    "tau": 0.15,
    "theta_end": 0.6,
}


@dataclass
class Span:
    chunk_ids: List[str]
    text: str
    page: int
    span: Tuple[int, int]
    flow_total: float


def _assert_efhg_enabled() -> None:
    assert cfg.HEADER_MODE != "preprocess_only", "EFHG disabled for headers"


def _style_similarity(a: UFChunk, b: UFChunk) -> float:
    denom = abs(a.style.get("font_size", 0.0)) + abs(b.style.get("font_size", 0.0)) + 1e-6
    font_sim = 1.0 - min(1.0, abs(a.style.get("font_size", 0.0) - b.style.get("font_size", 0.0)) / denom)
    indent_diff = abs(a.style.get("indent", 0.0) - b.style.get("indent", 0.0))
    indent_sim = 1.0 - min(1.0, indent_diff / 5.0)
    bold_sim = 1.0 if a.style.get("bold") == b.style.get("bold") else 0.6
    return (font_sim + indent_sim + bold_sim) / 3.0


def _parameter_overlap(a: UFChunk, b: UFChunk) -> float:
    set_a = set(a.lex.get("numbers", []))
    set_b = set(b.lex.get("numbers", []))
    if not set_a and not set_b:
        return 0.4
    if not set_a or not set_b:
        return 0.2
    overlap = len(set_a & set_b)
    total = len(set_a | set_b) or 1
    return overlap / total


def _header_consistency(a: UFChunk, b: UFChunk) -> float:
    if a.header_anchor and b.header_anchor:
        prefix_a = a.text.strip()[:3]
        prefix_b = b.text.strip()[:3]
        return 1.0 if prefix_a == prefix_b else 0.2
    if a.header_anchor or b.header_anchor:
        return 0.6
    return 0.4


def build_edges(uf_chunks: List[UFChunk], params: Dict[str, float] | None = None) -> Dict[Tuple[str, str], float]:
    _assert_efhg_enabled()
    params = params or DEFAULT_PARAMS
    edges: Dict[Tuple[str, str], float] = {}
    for i, left in enumerate(uf_chunks[:-1]):
        right = uf_chunks[i + 1]
        sem_sim = cosine(left.emb, right.emb)
        style_sim = _style_similarity(left, right)
        param_overlap = _parameter_overlap(left, right)
        header_consistency = _header_consistency(left, right)
        capacity = (
            params["alpha"] * sem_sim
            + params["beta"] * style_sim
            + params["gamma"] * param_overlap
            + params["delta"] * header_consistency
        )
        edges[(left.id, right.id)] = capacity
    return edges


def _span_text(chunk_lookup: Mapping[str, UFChunk], chunk_ids: Sequence[str]) -> Tuple[str, Tuple[int, int], int]:
    selected = [chunk_lookup[cid] for cid in chunk_ids]
    text = " ".join(chunk.text.strip() for chunk in selected).strip()
    start = selected[0].span_char[0]
    end = selected[-1].span_char[1]
    page = selected[0].page
    return text, (start, end), page


def span_from_chunk_ids(chunk_lookup: Mapping[str, UFChunk], chunk_ids: Sequence[str]) -> Span:
    _assert_efhg_enabled()
    text, span, page = _span_text(chunk_lookup, chunk_ids)
    return Span(chunk_ids=list(chunk_ids), text=text, page=page, span=span, flow_total=0.0)


def grow_span_from_seed(
    seed_id: str,
    uf_chunks: List[UFChunk],
    edges: Dict[Tuple[str, str], float],
    stop_scores: Dict[str, float],
    params: Dict[str, float] | None = None,
) -> Span:
    _assert_efhg_enabled()
    params = params or DEFAULT_PARAMS
    chunk_lookup = {chunk.id: chunk for chunk in uf_chunks}
    ordered_ids = [chunk.id for chunk in uf_chunks]
    if seed_id not in chunk_lookup:
        raise ValueError(f"Unknown seed chunk {seed_id}")
    idx = ordered_ids.index(seed_id)
    chain = [seed_id]
    marginals: List[Tuple[str, float]] = []
    current_id = seed_id
    while idx + 1 < len(ordered_ids):
        next_id = ordered_ids[idx + 1]
        if stop_scores.get(next_id, 0.0) >= params["theta_end"]:
            break
        capacity = edges.get((current_id, next_id), 0.0)
        marginal = capacity - params["lambda"]
        if marginal < params["tau"]:
            break
        marginals.append((next_id, marginal))
        current_id = next_id
        idx += 1

    best_total = 0.0
    best_end = -1
    running_total = 0.0
    running_start = 0
    best_start = 0
    for i, (_, marginal) in enumerate(marginals):
        running_total += marginal
        if running_total > best_total:
            best_total = running_total
            best_end = i
            best_start = running_start
        if running_total < 0:
            running_total = 0.0
            running_start = i + 1

    if best_end >= 0:
        chain.extend(cid for cid, _ in marginals[best_start : best_end + 1])
    text, span, page = _span_text(chunk_lookup, chain)
    return Span(chunk_ids=chain, text=text, page=page, span=span, flow_total=best_total)


__all__ = ["Span", "build_edges", "grow_span_from_seed", "span_from_chunk_ids", "DEFAULT_PARAMS"]
