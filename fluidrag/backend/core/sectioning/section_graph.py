"""Minimal graph construction utilities for sections."""
from __future__ import annotations

import re
from typing import Dict, Iterable, List


_REF_RE = re.compile(r"see\s+(?:section|§)\s*([A-Za-z0-9.]+)", re.IGNORECASE)


def build_section_graph(selected: Iterable[Dict]) -> Dict:
    """Create a deterministic graph representation for selected headers."""

    ordered = sorted(selected, key=lambda row: (row.get("page", 0), row.get("line_idx", 0)))
    nodes: List[Dict] = []
    edges: List[Dict] = []
    number_lookup: Dict[str, str] = {}

    for idx, record in enumerate(ordered):
        sec_id = f"S{idx:04d}"
        number = record.get("number") or record.get("num")
        title = record.get("title") or record.get("text_norm")
        nodes.append(
            {
                "sec_id": sec_id,
                "kind": record.get("kind"),
                "number": number,
                "title": title,
                "page": record.get("page"),
                "bbox_header": record.get("bbox"),
                "score": record.get("score"),
                "proto_sim_max": record.get("features", {}).get("proto_sim_max", 0.0),
                "canonical_id": record.get("canonical_id"),
                "canonical_conf": record.get("canonical_conf"),
                "text": record.get("text"),
            }
        )

        if number:
            normalized = str(number)
            number_lookup[normalized] = sec_id
            number_lookup[normalized.rstrip(".")]= sec_id
            number_lookup[normalized.rstrip(".)")]= sec_id

        if idx > 0:
            edges.append({"type": "NEXT", "from": f"S{idx-1:04d}", "to": sec_id})

    # REFERS_TO edges based on inline references
    for idx, record in enumerate(ordered):
        sec_id = f"S{idx:04d}"
        body_text = record.get("text") or ""
        if not body_text:
            continue
        for match in _REF_RE.finditer(body_text):
            token = match.group(1).rstrip(".")
            target = number_lookup.get(token)
            if target and target != sec_id:
                edges.append({"type": "REFERS_TO", "from": sec_id, "to": target})

    return {"nodes": nodes, "edges": edges}


__all__ = ["build_section_graph"]
