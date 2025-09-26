"""Helpers to build the graph sidecar from section and chunk metadata."""
from __future__ import annotations

from typing import Dict, Iterable, List

from .model import Graph


def build_graph(document_id: str, sections: Iterable[Dict], chunks: Iterable[Dict]) -> Graph:
    graph = Graph()
    graph.add_node(document_id, "Document", doc_id=document_id)

    section_nodes = {}
    for section in sections:
        node_id = section.get("sec_id") or section.get("section_id")
        section_nodes[node_id] = graph.add_node(node_id, "Section", **section)
        graph.add_edge("HAS_SECTION", document_id, node_id)

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id") or chunk.get("id")
        node = graph.add_node(chunk_id, "Chunk", **chunk)
        section_id = chunk.get("section_id")
        if section_id in section_nodes:
            graph.add_edge("HAS_CHUNK", section_id, chunk_id)

    ordered_sections = sorted(sections, key=lambda row: (row.get("page", 0), row.get("line_idx", 0)))
    for idx in range(1, len(ordered_sections)):
        prev_id = ordered_sections[idx - 1].get("sec_id")
        curr_id = ordered_sections[idx].get("sec_id")
        if prev_id and curr_id:
            graph.add_edge("NEXT", prev_id, curr_id)

    return graph


__all__ = ["build_graph"]
