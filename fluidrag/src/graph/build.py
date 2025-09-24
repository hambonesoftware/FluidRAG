from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from fluidrag.src.chunking.standard import Chunk

STANDARD_REGEX = re.compile(r"\b(?:ISO|IEC|NFPA|UL|IEEE|EN)\s?[0-9A-Za-z:\-]+\b", re.IGNORECASE)
CLAUSE_REGEX = re.compile(r"\b\d+(?:\.\d+){1,}\b")
QUANTITY_REGEX = re.compile(r"(?P<value>\d+(?:\.\d+)?)[\s\u00A0]*(?P<unit>(kA|A|V|Hz|mm|cm|m|%)\b)")
ENTITY_REGEX = re.compile(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)\b")


@dataclass
class Node:
    node_id: str
    node_type: str
    attributes: Dict[str, object]


@dataclass
class Edge:
    source: str
    target: str
    relation: str


@dataclass
class GraphArtifacts:
    nodes: List[Node]
    edges: List[Edge]
    summaries: List[Node]

    def write(self, base_path: Path) -> None:
        base_path.mkdir(parents=True, exist_ok=True)
        nodes_path = base_path / "nodes.jsonl"
        edges_path = base_path / "edges.jsonl"
        summaries_path = base_path / "summaries.jsonl"
        with nodes_path.open("w", encoding="utf-8") as f_nodes:
            for node in self.nodes:
                f_nodes.write(json.dumps(asdict(node), ensure_ascii=False) + "\n")
        with edges_path.open("w", encoding="utf-8") as f_edges:
            for edge in self.edges:
                f_edges.write(json.dumps(asdict(edge), ensure_ascii=False) + "\n")
        with summaries_path.open("w", encoding="utf-8") as f_summaries:
            for summary in self.summaries:
                f_summaries.write(json.dumps(asdict(summary), ensure_ascii=False) + "\n")


class GraphBuilder:
    def __init__(self, config: dict) -> None:
        self.config = config

    @staticmethod
    def _normalize_standard(ref: str) -> str:
        return re.sub(r"\s+", " ", ref.strip()).upper()

    @staticmethod
    def _normalize_clause(ref: str) -> str:
        return ref.strip()

    def build(self, doc_id: str, chunks: Sequence[Chunk]) -> GraphArtifacts:
        nodes: list[Node] = []
        edges: list[Edge] = []
        requirement_nodes: list[str] = []
        requirement_texts: dict[str, str] = {}
        communities: dict[int, list[str]] = defaultdict(list)

        for chunk in chunks:
            requirement_id = f"{chunk.chunk_id}:req"
            requirement_nodes.append(requirement_id)
            requirement_texts[requirement_id] = chunk.text
            nodes.append(Node(node_id=requirement_id, node_type="Requirement", attributes={"chunk": chunk.chunk_id}))

            if chunk.section_number:
                section_id = f"{doc_id}:section:{chunk.section_number}"
                nodes.append(
                    Node(
                        node_id=section_id,
                        node_type="Section",
                        attributes={"name": chunk.section_name or "", "section_number": chunk.section_number},
                    )
                )
                edges.append(Edge(source=section_id, target=requirement_id, relation="section_contains"))

            standards = {self._normalize_standard(match.group()) for match in STANDARD_REGEX.finditer(chunk.text)}
            clauses = {self._normalize_clause(match.group()) for match in CLAUSE_REGEX.finditer(chunk.text)}
            quantities = []
            for match in QUANTITY_REGEX.finditer(chunk.text):
                quantities.append(f"{match.group('value')}{match.group('unit')}")

            chunk.graph.setdefault("standard_refs", list(standards))
            chunk.graph.setdefault("clause_refs", list(clauses))
            chunk.graph.setdefault("quantity_ids", quantities)

            for standard in standards:
                node_id = f"standard:{standard}"
                nodes.append(Node(node_id=node_id, node_type="Standard", attributes={"label": standard}))
                edges.append(Edge(source=requirement_id, target=node_id, relation="requirement_refers_to"))

            for clause in clauses:
                node_id = f"clause:{clause}"
                nodes.append(Node(node_id=node_id, node_type="Clause", attributes={"label": clause}))
                edges.append(Edge(source=requirement_id, target=node_id, relation="requirement_refers_to"))

            for quantity in quantities:
                node_id = f"quantity:{quantity}"
                nodes.append(Node(node_id=node_id, node_type="Quantity", attributes={"value": quantity}))
                edges.append(Edge(source=requirement_id, target=node_id, relation="requirement_constrains"))

            entities = {match.group(1) for match in ENTITY_REGEX.finditer(chunk.text)}
            for entity in entities:
                node_id = f"entity:{entity.lower()}"
                nodes.append(Node(node_id=node_id, node_type="Entity", attributes={"label": entity}))
                edges.append(Edge(source=requirement_id, target=node_id, relation="requirement_mentions"))

        if requirement_nodes:
            # Simple community detection: group by first standard reference or fallback to document-level community 0
            for req_id in requirement_nodes:
                chunk_id = requirement_texts[req_id]
                text = requirement_texts[req_id]
                std_match = STANDARD_REGEX.search(text)
                community_id = hash(std_match.group().upper()) % 5 if std_match else 0
                communities[community_id].append(req_id)

        summary_nodes: list[Node] = []
        if self.config.get("graph", {}).get("summaries", {}).get("enabled", False):
            k = self.config["graph"]["summaries"].get("k", 2)
            for community_id, req_ids in communities.items():
                top_chunks = req_ids[:k]
                sentences = []
                for rid in top_chunks:
                    sentences.append(requirement_texts[rid].split(". ")[0])
                summary_text = " ".join(sentences)
                summary_nodes.append(
                    Node(
                        node_id=f"community:{community_id}",
                        node_type="CommunitySummary",
                        attributes={"summary": summary_text, "requirements": top_chunks},
                    )
                )
                for rid in req_ids:
                    edges.append(Edge(source=summary_nodes[-1].node_id, target=rid, relation="community_membership"))

        return GraphArtifacts(nodes=nodes, edges=edges, summaries=summary_nodes)


def build_graph(doc_id: str, chunks: Sequence[Chunk], output_dir: Path, config: dict) -> GraphArtifacts:
    builder = GraphBuilder(config)
    artifacts = builder.build(doc_id, chunks)
    builder_path = output_dir / doc_id
    artifacts.write(builder_path)
    return artifacts


__all__ = ["GraphBuilder", "GraphArtifacts", "build_graph", "Node", "Edge"]
