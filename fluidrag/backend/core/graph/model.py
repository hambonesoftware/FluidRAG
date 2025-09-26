"""Minimal data structures for the graph sidecar."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Node:
    id: str
    type: str
    data: Dict


@dataclass
class Edge:
    type: str
    source: str
    target: str
    data: Dict = field(default_factory=dict)


@dataclass
class Graph:
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)

    def add_node(self, node_id: str, node_type: str, **data) -> Node:
        node = Node(id=node_id, type=node_type, data=data)
        self.nodes.append(node)
        return node

    def add_edge(self, edge_type: str, source: str, target: str, **data) -> Edge:
        edge = Edge(type=edge_type, source=source, target=target, data=data)
        self.edges.append(edge)
        return edge


__all__ = ["Edge", "Graph", "Node"]
