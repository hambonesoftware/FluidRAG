"""Egocentric micrograph builder."""

from __future__ import annotations

import hashlib
import itertools
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Tuple

from .context import RAGContext
from .utils import normalize_text


_CACHE: Dict[str, Dict[str, Any]] = {}


def _hash_key(doc_id: str, ppass: str, seeds: Iterable[str]) -> str:
    joined = "|".join(sorted(normalize_text(s) for s in seeds))
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()
    return f"{doc_id}:{ppass}:{digest}"


def _extract_entities(text: str, vocab: Iterable[str]) -> List[str]:
    text_lower = text.lower()
    found = []
    for term in vocab:
        if term.lower() in text_lower:
            found.append(term)
    return found


def micrograph(query, candidate_sections, profile, context: RAGContext, seeds=None):
    cfg = profile.get("graphrag", {})
    vocab = cfg.get("entities", [])
    relations = cfg.get("relations", [])
    radius = cfg.get("radius", 1)
    max_comms = cfg.get("max_comms", 3)

    seeds = seeds or _extract_entities(query or "", vocab)
    if not seeds:
        return {"nodes": [], "edges": [], "communities": [], "summaries": []}

    cache_key = _hash_key(context.doc_id, context.ppass, seeds)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Tuple[str, str, str]] = []
    normalized_seeds = {normalize_text(s) for s in seeds}

    for section in candidate_sections:
        text = section.get("text") or section.get("section_name") or ""
        section_entities = _extract_entities(text, vocab)
        if radius <= 0:
            continue
        normalized_entities = {normalize_text(ent) for ent in section_entities}
        if normalized_seeds and not (normalized_entities & normalized_seeds):
            if radius <= 1:
                continue
        for ent in section_entities:
            if ent not in nodes:
                nodes[ent] = {
                    "id": ent,
                    "label": ent,
                    "anchors": section.get("anchors", []),
                    "pages": section.get("pages") or [section.get("page_start")],
                    "provenance": section.get("provenance") or [section.get("section_id")],
                }
        for src, dst in itertools.permutations(section_entities, 2):
            if src == dst:
                continue
            relation = next((rel for rel in relations if rel in text.lower()), "related_to")
            edges.append((src, dst, relation))

    # simple community detection: group by first letter bucket
    communities: Dict[str, List[str]] = defaultdict(list)
    for node_id in nodes:
        bucket = node_id[0].lower()
        communities[bucket].append(node_id)
    comm_items = sorted(communities.values(), key=len, reverse=True)[:max_comms]

    summaries = []
    for comm in comm_items:
        description = ", ".join(comm)
        citations = []
        for node_id in comm:
            node = nodes.get(node_id, {})
            anchors = node.get("anchors", [])
            citations.append(
                {
                    "anchor": anchors[0] if anchors else None,
                    "pages": node.get("pages", []),
                }
            )
        summaries.append({
            "community": list(comm),
            "summary": f"Entities connected: {description}",
            "citations": citations,
        })

    deduped_edges = []
    seen_edges = set()
    for src, dst, rel in edges:
        key = (src, dst, rel)
        if key in seen_edges:
            continue
        deduped_edges.append({"source": src, "target": dst, "relation": rel})
        seen_edges.add(key)

    result = {
        "nodes": list(nodes.values()),
        "edges": deduped_edges,
        "communities": comm_items,
        "summaries": summaries,
    }
    _CACHE[cache_key] = result
    return result
