from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from .build import GraphArtifacts, Node


@dataclass
class GraphContext:
    summaries: List[Node]
    nodes: List[Node]
    edges: List[Dict[str, str]]


def load_graph(doc_id: str, base_path: Path) -> GraphArtifacts | None:
    doc_path = base_path / doc_id
    nodes_path = doc_path / "nodes.jsonl"
    edges_path = doc_path / "edges.jsonl"
    summaries_path = doc_path / "summaries.jsonl"
    if not nodes_path.exists():
        return None

    def read_nodes(path: Path) -> List[Node]:
        if not path.exists():
            return []
        result: List[Node] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                payload = json.loads(line)
                result.append(Node(**payload))
        return result

    nodes = read_nodes(nodes_path)
    edges = []
    if edges_path.exists():
        with edges_path.open("r", encoding="utf-8") as f:
            for line in f:
                edges.append(json.loads(line))
    summaries = read_nodes(summaries_path)
    return GraphArtifacts(nodes=nodes, edges=edges, summaries=summaries)


def augment_with_graph(query: str, doc_id: str, base_path: Path, k_summaries: int = 2) -> GraphContext | None:
    artifacts = load_graph(doc_id, base_path)
    if not artifacts:
        return None

    summaries = artifacts.summaries[:k_summaries]
    return GraphContext(summaries=summaries, nodes=artifacts.nodes, edges=artifacts.edges)


__all__ = ["augment_with_graph", "load_graph", "GraphContext"]
