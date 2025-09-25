"""Augment existing stage payloads with microchunk and section metadata."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Sequence

from ingest import MicroChunk, assign_micro_to_sections, build_sections, microchunk_text


@dataclass
class StageBuildResult:
    doc_id: str
    payload: Dict[str, object]
    microchunks: List[MicroChunk]
    section_groups: List[Dict[str, object]]
    sections: List[Dict[str, object]]


def build_stage_payload(
    doc_id: str,
    stage_chunks: Sequence[Mapping[str, object]],
    *,
    token_size: int = 386,
    overlap: int = 96,
) -> StageBuildResult:
    """Return a stage payload extended with microchunks and section groups."""

    enriched_chunks: List[Dict[str, object]] = []
    for chunk in stage_chunks:
        part = dict(chunk)
        part["doc_id"] = doc_id
        enriched_chunks.append(part)

    microchunks = microchunk_text(enriched_chunks, size=token_size, overlap=overlap)
    sections = build_sections({"doc_id": doc_id, "chunks": stage_chunks})
    section_map = assign_micro_to_sections(microchunks, sections)

    section_lookup: Dict[str, Dict[str, object]] = {
        section["section_id"]: section for section in sections if section.get("section_id")
    }
    groups = [
        {
            "section_id": section_id,
            "title": section_lookup.get(section_id, {}).get("section_title", ""),
            "micro_ids": micro_ids,
        }
        for section_id, micro_ids in section_map.items()
    ]

    payload = {
        "doc_id": doc_id,
        "chunks": list(stage_chunks),
        "microchunking": {"token_size": token_size, "overlap": overlap, "count": len(microchunks)},
        "section_groups": groups,
    }
    return StageBuildResult(
        doc_id=doc_id,
        payload=payload,
        microchunks=microchunks,
        section_groups=groups,
        sections=list(sections),
    )


__all__ = ["StageBuildResult", "build_stage_payload"]
