"""Context packing utilities to match the legacy LLM payload shape."""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .types import Chunk, EvidenceBand


def _chunk_payload(chunk: Chunk) -> Dict[str, object]:
    payload = {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "section": chunk.section_no,
        "section_title": chunk.section_title,
        "pages": chunk.page_range,
        "text": chunk.text,
        "stage_tag": chunk.stage_tag,
        "resolution": chunk.resolution,
        "retrieval_scores": dict(chunk.retrieval_scores),
    }
    payload.update({f"meta_{key}": value for key, value in (chunk.meta or {}).items()})
    return payload


def _lookup_parent(chunk: Chunk, chunks_by_id: Dict[str, Chunk]) -> Optional[Dict[str, object]]:
    parent_id = chunk.meta.get("meso_parent_id") if chunk.meta else None
    if not parent_id:
        return None
    parent = chunks_by_id.get(parent_id)
    if parent is None:
        return None
    return _chunk_payload(parent)


def pack_context(
    band: EvidenceBand,
    chunks_by_id: Dict[str, Chunk],
    *,
    graph_summaries: Optional[Iterable[Dict[str, object]]] = None,
) -> Dict[str, List[Dict[str, object]]]:
    standards: List[Dict[str, object]] = []
    project_spec: List[Dict[str, object]] = []
    risk: List[Dict[str, object]] = []
    stage_routes: Dict[str, List[Dict[str, object]]] = {}
    for cid in band.band_chunk_ids:
        chunk = chunks_by_id.get(cid)
        if chunk is None:
            continue
        bucket = chunk.meta.get("bucket") if chunk.meta else None
        payload = _chunk_payload(chunk)
        parent_payload = _lookup_parent(chunk, chunks_by_id)
        if parent_payload is not None:
            payload["meso_parent"] = parent_payload
        stage_routes.setdefault(chunk.stage_tag, []).append(payload)
        if bucket == "Standards" or chunk.meta.get("standard_info"):
            standards.append(payload)
        elif bucket == "Risk" or chunk.meta.get("risk"):
            risk.append(payload)
        else:
            project_spec.append(payload)
    context = {
        "Standards": standards,
        "ProjectSpec": project_spec,
        "Risk": risk,
        "Stages": stage_routes,
    }
    if graph_summaries:
        context["GraphSummaries"] = list(graph_summaries)
    return context
