"""Micro-agent scoring models used by the RAG v2 pipeline."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, Iterable

from .config import CFG
from .graph import GraphIndex
from .types import Chunk


def _normalize(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    min_v = min(values)
    max_v = max(values)
    if math.isclose(max_v, min_v):
        return {cid: 0.5 for cid in scores}
    scale = max_v - min_v
    return {cid: (score - min_v) / scale for cid, score in scores.items()}


class StandardAgent:
    """Compute hybrid retrieval scores with optional cross-encoder signals."""

    def score(self, query: str, pool: Iterable[Chunk]) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for chunk in pool:
            dense = float(chunk.meta.get("dense_score", 0.0))
            bm25 = float(chunk.meta.get("bm25_score", chunk.bm25 or 0.0))
            regex_hits = float(chunk.meta.get("regex_hits", chunk.regex_hits or 0))
            base = (0.6 * dense) + (0.3 * bm25) + (0.1 * regex_hits)
            cross = float(chunk.meta.get("crossenc_score", 0.0))
            if cross:
                base = 0.7 * base + 0.3 * cross
            scores[chunk.chunk_id] = base
        return _normalize(scores)


class FluidAgent:
    """Diffusion-based smoothing of the standard agent scores across a similarity graph."""

    def __init__(self, lam: float = 0.85, steps: int = 4) -> None:
        self._lam = lam
        self._steps = steps

    def score(self, query: str, pool: Iterable[Chunk], graph: GraphIndex) -> Dict[str, float]:
        base = {chunk.chunk_id: float(chunk.meta.get("hybrid_score", 0.5)) for chunk in pool}
        if not base:
            return {}
        ids = list(base.keys())
        rank = {cid: base[cid] for cid in ids}
        for _ in range(self._steps):
            updated: Dict[str, float] = {}
            for cid in ids:
                neighbors = graph.neighbors(cid, CFG.max_neighbors)
                if not neighbors:
                    updated[cid] = base[cid]
                    continue
                total = 0.0
                weight_sum = 0.0
                for nid, weight in neighbors:
                    weight_sum += weight
                    total += weight * rank.get(nid, base.get(nid, 0.0))
                neighbor_avg = total / weight_sum if weight_sum else base[cid]
                updated[cid] = (self._lam * neighbor_avg) + ((1 - self._lam) * base[cid])
            rank = updated
        return _normalize(rank)


class HEPAgent:
    """High-entropy precision agent scoring information dense passages."""

    _number_re = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)")
    _unit_re = re.compile(r"\b(?:mm|cm|m|in|ft|hz|khz|°c|°f|psi|bar|nm|kw|ma|vdc)\b", re.I)

    def score(self, query: str, pool: Iterable[Chunk]) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        facets = [token.lower() for token in query.split() if len(token) > 3]
        for chunk in pool:
            text = chunk.text
            numbers = len(self._number_re.findall(text))
            units = len(self._unit_re.findall(text))
            std_ids = len(chunk.meta.get("std_ids", []))
            density = (
                (CFG.w_num * numbers)
                + (CFG.w_unit * units)
                + (CFG.w_stdID * std_ids)
            )
            tokens = [token.lower() for token in re.findall(r"\w+", text)]
            total = len(tokens) or 1
            counts = Counter(tokens)
            entropy = 0.0
            for count in counts.values():
                p = count / total
                entropy -= p * math.log(max(p, 1e-6))
            entropy /= math.log(total + 1)
            window = " ".join(tokens[: CFG.facet_window_tokens])
            collisions = sum(1 for facet in facets if facet in window)
            score = density * (1.0 + CFG.hep_entropy_kappa * entropy) + (0.1 * collisions)
            scores[chunk.chunk_id] = score
        return _normalize(scores)
