"""Context packing utilities to match the legacy LLM payload shape."""
from __future__ import annotations

from typing import Dict, List

from .types import Chunk, EvidenceBand


def _chunk_payload(chunk: Chunk) -> Dict[str, object]:
    payload = {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "section": chunk.section_no,
        "section_title": chunk.section_title,
        "pages": chunk.page_range,
        "text": chunk.text,
    }
    payload.update({f"meta_{key}": value for key, value in (chunk.meta or {}).items()})
    return payload


def pack_context(
    band: EvidenceBand, chunks_by_id: Dict[str, Chunk]
) -> Dict[str, List[Dict[str, object]]]:
    standards: List[Dict[str, object]] = []
    project_spec: List[Dict[str, object]] = []
    risk: List[Dict[str, object]] = []
    for cid in band.band_chunk_ids:
        chunk = chunks_by_id.get(cid)
        if chunk is None:
            continue
        bucket = chunk.meta.get("bucket") if chunk.meta else None
        payload = _chunk_payload(chunk)
        if bucket == "Standards" or chunk.meta.get("standard_info"):
            standards.append(payload)
        elif bucket == "Risk" or chunk.meta.get("risk"):
            risk.append(payload)
        else:
            project_spec.append(payload)
    return {
        "Standards": standards,
        "ProjectSpec": project_spec,
        "Risk": risk,
    }
