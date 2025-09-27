"""EFHG scoring over UF chunks.

The module implements a lightweight approximation of the EFHG rail described in
the system design.  The goal is not to emulate a production-scale graph
pipeline, but to provide deterministic heuristics that mimic the scoring
signals.  The helpers operate directly on the UF chunk dictionaries emitted by
``ingest.microchunker`` and return span descriptors enriched with the per-stage
sub scores.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from backend.headers import config as cfg


def _assert_efhg_enabled() -> None:
    """Ensure EFHG helpers are not invoked while disabled."""

    assert cfg.HEADER_MODE != "preprocess_only", "EFHG disabled for headers"


@dataclass
class _ChunkView:
    idx: int
    data: Mapping[str, object]
    tokens: List[str]
    entropy: float
    modalness: float
    header_weight: float
    stop_punct: float
    params: Dict[str, List[str]]


def _tokenize(text: str) -> List[str]:
    text = (text or "").lower()
    return [tok for tok in text.replace("/", " ").split() if tok]


def _entropy(tokens: Iterable[str]) -> float:
    freq: Dict[str, int] = {}
    total = 0
    for tok in tokens:
        freq[tok] = freq.get(tok, 0) + 1
        total += 1
    if total <= 1:
        return 0.0
    ent = 0.0
    for count in freq.values():
        p = count / total
        ent -= p * math.log(p + 1e-9, 2)
    return ent


def _modalness(chunk: Mapping[str, object]) -> float:
    lex = chunk.get("lex")
    if isinstance(lex, Mapping):
        flags = lex.get("modal_flags") or []
        if flags:
            return min(1.0, len(flags) / 2)
    text = str(chunk.get("norm_text") or chunk.get("text") or "").lower()
    hits = sum(1 for term in ("shall", "must", "should", "will") if term in text)
    return min(1.0, hits / 2)


def _header_weight(chunk: Mapping[str, object]) -> float:
    weight = 0.0
    if chunk.get("header_anchor"):
        weight += 0.4
    if chunk.get("section_id"):
        weight += 0.4
    if chunk.get("section_title"):
        weight += 0.2
    return min(weight, 1.0)


def _terminal_punct(chunk: Mapping[str, object]) -> float:
    text = str(chunk.get("text") or "").strip()
    if not text:
        return 0.0
    return 1.0 if text.endswith(('.', ';')) else 0.0


def _collect_params(chunk: Mapping[str, object]) -> Dict[str, List[str]]:
    params: Dict[str, List[str]] = {"numbers": [], "units": []}
    lex = chunk.get("lex")
    if isinstance(lex, Mapping):
        for key in ("numbers", "units"):
            values = lex.get(key)
            if isinstance(values, list):
                params[key] = [str(v) for v in values]
    return params


def _prepare_chunks(chunks: Sequence[Mapping[str, object]]) -> List[_ChunkView]:
    prepared: List[_ChunkView] = []
    for idx, chunk in enumerate(chunks):
        tokens = _tokenize(str(chunk.get("norm_text") or chunk.get("text") or ""))
        ent = _entropy(tokens)
        modal = _modalness(chunk)
        header_weight = _header_weight(chunk)
        stop = _terminal_punct(chunk)
        params = _collect_params(chunk)
        prepared.append(
            _ChunkView(
                idx=idx,
                data=chunk,
                tokens=tokens,
                entropy=ent,
                modalness=modal,
                header_weight=header_weight,
                stop_punct=stop,
                params=params,
            )
        )
    return prepared


def _delta(values: Sequence[float]) -> List[float]:
    result: List[float] = []
    for idx, value in enumerate(values):
        prev = values[idx - 1] if idx > 0 else value
        nxt = values[idx + 1] if idx + 1 < len(values) else value
        result.append((nxt - prev) / 2.0)
    return result


def _capacity(a: _ChunkView, b: _ChunkView) -> float:
    if a.data.get("page") and b.data.get("page") and a.data.get("page") != b.data.get("page"):
        return 0.0

    token_overlap = len(set(a.tokens) & set(b.tokens)) / max(1, len(set(a.tokens) | set(b.tokens)))

    style_a = a.data.get("style") if isinstance(a.data.get("style"), Mapping) else {}
    style_b = b.data.get("style") if isinstance(b.data.get("style"), Mapping) else {}
    indent_a = float(style_a.get("indent") or 0.0)
    indent_b = float(style_b.get("indent") or 0.0)
    indent_gap = abs(indent_a - indent_b)
    style_score = 1.0 - min(indent_gap / 40.0, 1.0)

    param_overlap = 0.0
    if a.params["numbers"] and b.params["numbers"]:
        param_overlap += len(set(a.params["numbers"]) & set(b.params["numbers"]))
    if a.params["units"] and b.params["units"]:
        param_overlap += len(set(a.params["units"]) & set(b.params["units"]))
    param_overlap = min(param_overlap / 4.0, 1.0)

    header_a = a.data.get("section_id") or a.data.get("header_anchor")
    header_b = b.data.get("section_id") or b.data.get("header_anchor")
    header_score = 1.0 if header_a and header_a == header_b else 0.2 if header_a and header_b else 0.0

    return max(0.0, min(1.0, 0.8 * token_overlap + 0.4 * style_score + 0.5 * param_overlap + 0.3 * header_score))


def compute_chunk_scores(chunks: Sequence[Mapping[str, object]]) -> List[Dict[str, float]]:
    """Return per chunk E/F start-stop features."""

    prepared = _prepare_chunks(chunks)
    if not prepared:
        return []

    entropies = [p.entropy for p in prepared]
    entropy_delta = _delta(entropies)

    results: List[Dict[str, float]] = []
    for idx, chunk in enumerate(prepared):
        start_score = -entropy_delta[idx] + 1.2 * chunk.modalness + 0.8 * chunk.header_weight
        stop_score = entropy_delta[idx] + chunk.stop_punct + 0.6 * (1.0 - chunk.modalness)
        results.append(
            {
                "S_start": round(start_score, 4),
                "S_stop": round(stop_score, 4),
                "entropy": round(chunk.entropy, 4),
                "modalness": round(chunk.modalness, 4),
                "header_weight": round(chunk.header_weight, 4),
                "stop_punct": round(chunk.stop_punct, 4),
            }
        )
    return results


def _hep_score(span: Sequence[_ChunkView]) -> Tuple[float, Dict[str, object]]:
    modal = sum(chunk.modalness for chunk in span)
    numbers = sum(1 for chunk in span if chunk.params["numbers"])
    citations = sum(1 for chunk in span if chunk.data.get("lex", {}).get("citation_hint"))
    actors = any("shall" in " ".join(chunk.tokens) for chunk in span)
    ambiguity_terms = sum(
        1
        for chunk in span
        if "etc" in chunk.tokens or "as" in chunk.tokens or "needed" in chunk.tokens
    )
    ambiguity_penalty = 0.3 * ambiguity_terms
    score = modal + 0.9 * numbers + 0.6 * citations + 0.8 * bool(actors) - ambiguity_penalty
    details: Dict[str, object] = {
        "modal_sum": round(modal, 4),
        "constraint_hits": int(numbers),
        "citation_hits": int(citations),
        "actor_present": bool(actors),
        "ambiguity_terms": int(ambiguity_terms),
        "penalty": round(ambiguity_penalty, 4),
    }
    return score, details


def _graph_penalty(span: Sequence[_ChunkView]) -> Tuple[float, Dict[str, object]]:
    headers = {chunk.data.get("section_id") for chunk in span if chunk.data.get("section_id")}
    header_conflict = len(headers) > 1
    anchors = {chunk.data.get("header_anchor") for chunk in span if chunk.data.get("header_anchor")}
    anchor_conflict = len(anchors) > 1
    penalty = 0.0
    conflicts: List[str] = []
    if header_conflict:
        penalty += 1.0
        conflicts.append("header_mismatch")
    if anchor_conflict:
        penalty += 0.6
        conflicts.append("anchor_mismatch")
    details: Dict[str, object] = {
        "header_conflict": header_conflict,
        "anchor_conflict": anchor_conflict,
        "conflicts": conflicts,
    }
    return penalty, details


def compute_fluid_neighbors(chunks: Sequence[Mapping[str, object]]) -> List[Dict[str, object]]:
    """Return adjacency summaries for each chunk using the Fluid capacity metric."""

    _assert_efhg_enabled()

    prepared = _prepare_chunks(chunks)
    if not prepared:
        return []

    neighbors: List[Dict[str, object]] = []
    for idx, chunk in enumerate(prepared):
        entry: Dict[str, object] = {
            "index": idx,
            "micro_id": chunk.data.get("micro_id"),
        }
        if idx > 0:
            prev = prepared[idx - 1]
            cap = _capacity(prev, chunk)
            if cap > 0.0:
                entry["prev"] = {
                    "index": idx - 1,
                    "micro_id": prev.data.get("micro_id"),
                    "capacity": round(cap, 4),
                }
        if idx + 1 < len(prepared):
            nxt = prepared[idx + 1]
            cap = _capacity(chunk, nxt)
            if cap > 0.0:
                entry["next"] = {
                    "index": idx + 1,
                    "micro_id": nxt.data.get("micro_id"),
                    "capacity": round(cap, 4),
                }
        neighbors.append(entry)
    return neighbors


def run_efhg(chunks: Sequence[Mapping[str, object]]) -> List[Dict[str, object]]:
    """Compute EFHG spans for the provided UF chunks."""

    if cfg.HEADER_MODE == "preprocess_only":
        return []

    _assert_efhg_enabled()

    prepared = _prepare_chunks(chunks)
    if not prepared:
        return []

    scores = compute_chunk_scores(chunks)
    start_scores = [entry["S_start"] for entry in scores]
    threshold = sorted(start_scores)[max(0, int(len(start_scores) * 0.85) - 1)] if start_scores else 0.0

    spans: List[Dict[str, object]] = []
    used_indices: set = set()

    for view, metrics in zip(prepared, scores):
        if metrics["S_start"] < threshold or view.idx in used_indices:
            continue

        span_chunks: List[_ChunkView] = [view]
        gain = metrics["S_start"]
        flow_edges: List[Dict[str, object]] = []

        for candidate in prepared[view.idx + 1 :]:
            if candidate.idx in used_indices:
                break
            cap = _capacity(span_chunks[-1], candidate)
            if cap <= 0.05:
                break
            span_chunks.append(candidate)
            gain += cap
            flow_edges.append(
                {
                    "from": span_chunks[-2].idx,
                    "to": candidate.idx,
                    "capacity": round(cap, 4),
                }
            )
            if compute_chunk_scores([candidate.data])[0]["S_stop"] > 1.5:
                break

        hep, hep_details = _hep_score(span_chunks)
        graph_penalty, graph_details = _graph_penalty(span_chunks)
        total_score = hep + gain - graph_penalty
        if total_score < 1.5:
            continue

        used_indices.update(chunk.idx for chunk in span_chunks)
        span_text = " ".join(chunk.data.get("text", "") for chunk in span_chunks)
        spans.append(
            {
                "start_index": span_chunks[0].idx,
                "end_index": span_chunks[-1].idx,
                "score": round(total_score, 4),
                "E": round(sum(chunk.entropy for chunk in span_chunks) / len(span_chunks), 4),
                "F": round(gain, 4),
                "H": round(hep, 4),
                "G_penalty": round(graph_penalty, 4),
                "components": {
                    "flow": {
                        "start_seed": round(metrics["S_start"], 4),
                        "edges": flow_edges,
                        "total": round(gain, 4),
                    },
                    "hep": {
                        "score": round(hep, 4),
                        **hep_details,
                    },
                    "graph": {
                        "penalty": round(graph_penalty, 4),
                        **graph_details,
                    },
                },
                "chunk_indices": [chunk.idx for chunk in span_chunks],
                "preview": span_text[:120],
            }
        )

    spans.sort(key=lambda item: item["score"], reverse=True)
    return spans


__all__ = ["compute_chunk_scores", "compute_fluid_neighbors", "run_efhg"]

