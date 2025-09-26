from __future__ import annotations

import math
from typing import Dict, Iterable, List

from backend.uf_chunker import HEADER_PATTERN, UFChunk

DEFAULT_WEIGHTS = {
    "w1": 0.7,
    "w2": 0.2,
    "w3": 0.1,
    "w4": 0.6,
    "w5": 0.25,
    "w6": 0.15,
}
DEFAULT_SEED_QUANTILE = 0.85  # top 15%
DEFAULT_STOP_QUANTILE = 0.80  # top 20%


def _tokenize(text: str) -> List[str]:
    return [tok for tok in text.replace("\n", " ").split(" ") if tok]


def _entropy(values: Iterable[float]) -> float:
    total = sum(values)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for value in values:
        if value <= 0:
            continue
        prob = value / total
        entropy -= prob * math.log(prob, 2)
    return entropy


def _header_proximity(chunk: UFChunk) -> float:
    if chunk.header_anchor:
        return 1.0
    first_line = chunk.text.strip().splitlines()[0] if chunk.text.strip() else ""
    return 0.6 if HEADER_PATTERN.match(first_line) else 0.1


def _terminal_punct(chunk: UFChunk) -> float:
    return 1.0 if chunk.text.strip().endswith((".", ";")) else 0.0


def _no_new_params_ahead(chunk: UFChunk) -> float:
    return 1.0 if not chunk.lex.get("numbers") else 0.2


def compute_entropy_features(uf_chunks: List[UFChunk]) -> None:
    """Annotate each UF chunk with entropy-derived statistics."""

    for chunk in uf_chunks:
        tokens = _tokenize(chunk.text)
        token_lengths = [len(tok) for tok in tokens] or [1]
        positional = list(range(1, len(tokens) + 1)) or [1]
        h_tkn = _entropy(token_lengths)
        h_pos = _entropy(positional)
        chunk.entropy = {
            "H_tkn": h_tkn,
            "H_pos": h_pos,
            "modal": 1.0 if chunk.lex.get("has_modal") else 0.0,
        }

    for idx, chunk in enumerate(uf_chunks):
        prev_h = uf_chunks[idx - 1].entropy.get("H_tkn", 0.0) if idx > 0 else chunk.entropy.get("H_tkn", 0.0)
        next_h = uf_chunks[idx + 1].entropy.get("H_tkn", 0.0) if idx + 1 < len(uf_chunks) else chunk.entropy.get("H_tkn", 0.0)
        chunk.entropy["dH_prev"] = chunk.entropy.get("H_tkn", 0.0) - prev_h
        chunk.entropy["dH_next"] = next_h - chunk.entropy.get("H_tkn", 0.0)


def score_starts(uf_chunks: List[UFChunk], weights: Dict[str, float] | None = None) -> Dict[str, float]:
    """Compute start likelihood scores for UF chunks."""

    weights = weights or DEFAULT_WEIGHTS
    scores: Dict[str, float] = {}
    for chunk in uf_chunks:
        dH_prev = chunk.entropy.get("dH_prev", 0.0)
        modalness = chunk.entropy.get("modal", 0.0)
        proximity = _header_proximity(chunk)
        scores[chunk.id] = (
            weights["w1"] * (-dH_prev)
            + weights["w2"] * modalness
            + weights["w3"] * proximity
        )
    return scores


def score_stops(uf_chunks: List[UFChunk], weights: Dict[str, float] | None = None) -> Dict[str, float]:
    """Compute stop likelihood scores for UF chunks."""

    weights = weights or DEFAULT_WEIGHTS
    scores: Dict[str, float] = {}
    for chunk in uf_chunks:
        dH_next = chunk.entropy.get("dH_next", 0.0)
        terminal = _terminal_punct(chunk)
        params = _no_new_params_ahead(chunk)
        scores[chunk.id] = (
            weights["w4"] * (+dH_next)
            + weights["w5"] * terminal
            + weights["w6"] * params
        )
    return scores


def select_quantile_ids(scores: Dict[str, float], quantile: float) -> List[str]:
    if not scores:
        return []
    values = sorted(scores.values())
    index = max(0, min(len(values) - 1, int(math.floor(quantile * (len(values) - 1)))))
    threshold = values[index]
    return [cid for cid, score in scores.items() if score >= threshold]


__all__ = [
    "compute_entropy_features",
    "score_starts",
    "score_stops",
    "select_quantile_ids",
    "DEFAULT_SEED_QUANTILE",
    "DEFAULT_STOP_QUANTILE",
    "DEFAULT_WEIGHTS",
]
