"""Similarity graph structures used by Fluid agent and entropy carving."""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from .config import CFG


class GraphIndex:
    """Lightweight adjacency list representation of chunk similarity."""

    def __init__(self) -> None:
        self._adjacency: Dict[str, List[Tuple[str, float]]] = defaultdict(list)

    def add_edge(self, source: str, target: str, weight: float) -> None:
        if source == target:
            return
        if weight < CFG.tau_sim_edge:
            return
        self._adjacency[source].append((target, float(weight)))

    def add_bidirectional(self, a: str, b: str, weight: float) -> None:
        self.add_edge(a, b, weight)
        self.add_edge(b, a, weight)

    def neighbors(self, chunk_id: str, top: int | None = None) -> List[Tuple[str, float]]:
        candidates = list(self._adjacency.get(chunk_id, ()))
        candidates.sort(key=lambda item: item[1], reverse=True)
        if top is not None and top > 0:
            candidates = candidates[:top]
        return candidates

    def degree(self, chunk_id: str) -> int:
        return len(self._adjacency.get(chunk_id, ()))

    def build_from_edges(
        self, edges: Iterable[Tuple[str, str, float]], *, bidirectional: bool = True
    ) -> None:
        for source, target, weight in edges:
            if bidirectional:
                self.add_bidirectional(source, target, weight)
            else:
                self.add_edge(source, target, weight)

    def as_dict(self) -> Dict[str, List[Tuple[str, float]]]:
        return {node: list(neighbors) for node, neighbors in self._adjacency.items()}
