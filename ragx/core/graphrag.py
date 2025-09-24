"""Egocentric micrograph builder."""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .context import RAGContext
from .utils import normalize_text


_CACHE: Dict[str, Dict[str, Any]] = {}


def _hash_key(doc_id: str, ppass: str, version: str, seeds: Iterable[str]) -> str:
    joined = "|".join(sorted(normalize_text(s) for s in seeds))
    digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()
    return f"{doc_id}:{ppass}:{version}:{digest}"


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

    cache_key = _hash_key(context.doc_id, context.ppass, context.version, seeds)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Tuple[str, str, str]] = []

    for section in candidate_sections:
        text = section.get("text") or section.get("section_name") or ""
        section_entities = _extract_entities(text, vocab)
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
        summaries.append({
            "community": list(comm),
            "summary": f"Entities connected: {description}",
        })

    result = {
        "nodes": list(nodes.values()),
        "edges": [
            {"source": s, "target": t, "relation": rel} for s, t, rel in edges
        ],
        "communities": comm_items,
        "summaries": summaries,
    }
    _CACHE[cache_key] = result
    return result
