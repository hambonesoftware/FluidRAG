"""Entropy based evidence band selection strategies."""
from __future__ import annotations

import math
import re
from typing import Dict, Iterable, List, Sequence

from .config import CFG
from .graph import GraphIndex
from .types import Chunk, EvidenceBand

_token_re = re.compile(r"\w+")


def _window_entropy(chunks: Sequence[Chunk]) -> float:
    tokens: List[str] = []
    for chunk in chunks:
        tokens.extend(token.lower() for token in _token_re.findall(chunk.text))
    if not tokens:
        return 0.0
    total = len(tokens)
    counts: Dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log(max(p, 1e-9))
    return entropy / math.log(total + 1)


def _collect_window(ordered: Sequence[Chunk], start: int, end: int) -> List[Chunk]:
    start = max(0, start)
    end = min(len(ordered), end)
    return list(ordered[start:end])


def entropy_linear_band(seed_idx: int, ordered: Sequence[Chunk]) -> EvidenceBand:
    window = CFG.entropy_window_chunks
    entropy_left: List[float] = []
    entropy_right: List[float] = []
    left = seed_idx
    right = seed_idx + 1
    prev_entropy = 0.0
    while left > 0:
        left -= 1
        series = _collect_window(ordered, left, left + window)
        value = _window_entropy(series)
        entropy_left.append(value)
        if value > CFG.tau_entropy_abs or abs(value - prev_entropy) > CFG.tau_entropy_grad:
            left += 1
            break
        prev_entropy = value
    prev_entropy = 0.0
    while right < len(ordered):
        series = _collect_window(ordered, right - window + 1, right + 1)
        value = _window_entropy(series)
        entropy_right.append(value)
        if value > CFG.tau_entropy_abs or abs(value - prev_entropy) > CFG.tau_entropy_grad:
            right -= 1
            break
        prev_entropy = value
        right += 1
    right = min(len(ordered) - 1, max(right, seed_idx))
    band_ids = [chunk.chunk_id for chunk in ordered[left : right + 1]]
    avg_entropy = 0.0
    if entropy_left or entropy_right:
        avg_entropy = sum(entropy_left + entropy_right) / max(
            len(entropy_left + entropy_right), 1
        )
    confidence = max(0.35, 1.0 - avg_entropy)
    return EvidenceBand(
        seed_chunk_id=ordered[seed_idx].chunk_id,
        start_idx=left,
        end_idx=right,
        confidence=confidence,
        entropy_trace_left=entropy_left,
        entropy_trace_right=entropy_right,
        method="linear_entropy",
        band_chunk_ids=band_ids,
    )


def entropy_graph_band(
    seed_chunk: Chunk, pool: Sequence[Chunk], graph: GraphIndex
) -> EvidenceBand:
    visited = {seed_chunk.chunk_id}
    frontier = [(seed_chunk.chunk_id, 1.0)]
    band_ids = [seed_chunk.chunk_id]
    entropy_trace: List[float] = []
    while frontier:
        current, weight = frontier.pop(0)
        neighbors = graph.neighbors(current, CFG.max_neighbors)
        for neighbor, sim in neighbors:
            if neighbor in visited:
                continue
            visited.add(neighbor)
            frontier.append((neighbor, sim))
            chunk = next((c for c in pool if c.chunk_id == neighbor), None)
            if chunk is None:
                continue
            candidate_band = band_ids + [neighbor]
            chunks = [c for c in pool if c.chunk_id in candidate_band]
            value = _window_entropy(chunks)
            entropy_trace.append(value)
            if value > CFG.tau_entropy_frontier:
                continue
            band_ids.append(neighbor)
    idx_map = {chunk.chunk_id: idx for idx, chunk in enumerate(pool)}
    positions = [idx_map.get(cid, 0) for cid in band_ids]
    start = min(positions)
    end = max(positions)
    confidence = max(0.4, 1.0 - (sum(entropy_trace) / (len(entropy_trace) or 1)))
    return EvidenceBand(
        seed_chunk_id=seed_chunk.chunk_id,
        start_idx=start,
        end_idx=end,
        confidence=confidence,
        entropy_trace_left=entropy_trace,
        entropy_trace_right=[],
        method="graph_diffusion_entropy",
        band_chunk_ids=band_ids,
    )


def entropy_changepoint_band(seed_idx: int, ordered: Sequence[Chunk]) -> EvidenceBand:
    window = max(1, CFG.entropy_window_chunks)
    entropies = [
        _window_entropy(_collect_window(ordered, idx, idx + window))
        for idx in range(len(ordered))
    ]
    left = seed_idx
    right = seed_idx
    while left > 0:
        if abs(entropies[left] - entropies[left - 1]) > CFG.tau_entropy_grad:
            break
        left -= 1
    while right < len(ordered) - 1:
        if abs(entropies[right + 1] - entropies[right]) > CFG.tau_entropy_grad:
            break
        right += 1
    left = max(0, left - CFG.entropy_buffer_chunks)
    right = min(len(ordered) - 1, right + CFG.entropy_buffer_chunks)
    band_ids = [chunk.chunk_id for chunk in ordered[left : right + 1]]
    avg = sum(entropies[left : right + 1]) / max(1, (right - left + 1))
    confidence = max(0.4, 1.0 - avg)
    return EvidenceBand(
        seed_chunk_id=ordered[seed_idx].chunk_id,
        start_idx=left,
        end_idx=right,
        confidence=confidence,
        entropy_trace_left=entropies[: seed_idx],
        entropy_trace_right=entropies[seed_idx + 1 :],
        method="entropy_changepoint",
        band_chunk_ids=band_ids,
    )
