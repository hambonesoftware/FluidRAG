"""Simple traversal helpers for the graph sidecar."""
from __future__ import annotations

from typing import List

from .model import Graph


def neighbors(graph: Graph, node_id: str, edge_type: str) -> List[str]:
    return [edge.target for edge in graph.edges if edge.source == node_id and edge.type == edge_type]


__all__ = ["neighbors"]
