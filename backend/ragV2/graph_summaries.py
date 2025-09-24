"""Graph-based summarisation utilities for comparative queries."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .types import Chunk

STANDARD_RE = re.compile(r"\b(?:NFPA|IEC|ISO|UL|OSHA|EN)\s?[\dA-Z]+\b")
RELATION_RE = re.compile(r"\b(?:refer|align|conform|compare|versus|vs\.?|per)\b", re.I)


@dataclass
class GraphSummary:
    """Light-weight representation of a clustered summary."""

    community_id: str
    text: str
    citations: List[str]

    def to_payload(self) -> Dict[str, object]:
        return {"id": self.community_id, "summary": self.text, "citations": self.citations}


def _extract_entities(chunk: Chunk) -> List[str]:
    matches = STANDARD_RE.findall(chunk.text or "")
    extra = chunk.meta.get("standards", []) if chunk.meta else []
    return sorted({*(m.upper() for m in matches), *(str(s).upper() for s in extra)})


def _co_occurrence_graph(chunks: Sequence[Chunk]) -> Dict[str, Dict[str, float]]:
    graph: Dict[str, Dict[str, float]] = {}
    for chunk in chunks:
        entities = _extract_entities(chunk)
        if len(entities) < 2:
            continue
        weight = 1.0 + 0.5 * sum(1 for _ in RELATION_RE.finditer(chunk.text or ""))
        for a in entities:
            graph.setdefault(a, {})
            for b in entities:
                if a == b:
                    continue
                graph[a][b] = graph[a].get(b, 0.0) + weight
    return graph


def _community_assignments(graph: Dict[str, Dict[str, float]]) -> Dict[str, int]:
    community: Dict[str, int] = {}
    current = 0
    visited: Dict[str, bool] = {}
    for node in graph:
        if visited.get(node):
            continue
        stack = [node]
        while stack:
            current_node = stack.pop()
            if visited.get(current_node):
                continue
            visited[current_node] = True
            community[current_node] = current
            for neighbor, weight in graph.get(current_node, {}).items():
                if weight >= 1.0 and not visited.get(neighbor):
                    stack.append(neighbor)
        current += 1
    return community


def _sentence_rank(chunk: Chunk, entities: Sequence[str]) -> List[Tuple[float, str]]:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", chunk.text or "") if sentence.strip()]
    ranked: List[Tuple[float, str]] = []
    for sentence in sentences:
        hits = sum(sentence.upper().count(entity) for entity in entities)
        if hits == 0:
            continue
        length = max(len(sentence.split()), 1)
        score = hits / length
        ranked.append((score, sentence))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[:2]


def build_graph_summaries(chunks: Sequence[Chunk], top_k: int = 3) -> List[GraphSummary]:
    if not chunks:
        return []
    graph = _co_occurrence_graph(chunks)
    community_map = _community_assignments(graph)
    buckets: Dict[int, List[Chunk]] = {}
    for chunk in chunks:
        entities = _extract_entities(chunk)
        if not entities:
            continue
        communities = {community_map.get(entity) for entity in entities if entity in community_map}
        for community_id in communities:
            if community_id is None:
                continue
            buckets.setdefault(community_id, []).append(chunk)

    summaries: List[GraphSummary] = []
    for community_id, members in buckets.items():
        if not members:
            continue
        all_entities = sorted({entity for chunk in members for entity in _extract_entities(chunk)})
        sentence_pool: List[Tuple[float, str, Chunk]] = []
        for chunk in members:
            ranked = _sentence_rank(chunk, all_entities)
            for score, sentence in ranked:
                sentence_pool.append((score, sentence, chunk))
        sentence_pool.sort(key=lambda item: item[0], reverse=True)
        selected = sentence_pool[: max(2, min(5, len(sentence_pool)))]
        if not selected:
            continue
        joined = " ".join(sentence for _score, sentence, _chunk in selected)
        citations = sorted({f"{item[2].doc_id}:{item[2].page_range[0]}" for item in selected})
        summaries.append(
            GraphSummary(
                community_id=f"community-{community_id}",
                text=joined,
                citations=citations,
            )
        )

    summaries.sort(key=lambda summary: (-len(summary.citations), summary.community_id))
    return summaries[:top_k]

