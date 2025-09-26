"""Augment existing stage payloads with microchunk and section metadata."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Sequence

from ingest import MicroChunk, assign_micro_to_sections, build_sections, microchunk_text

_DEFAULT_DEBUG_DIR = Path("debug") / "chunks"


def _debug_dir() -> Path:
    env_override = os.environ.get("FLUIDRAG_DEBUG_DIR")
    if env_override:
        base = Path(env_override)
    else:
        base = _DEFAULT_DEBUG_DIR
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sanitize_doc_id(doc_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in doc_id)
    return safe or "doc"


def _write_microchunk_debug(doc_id: str, microchunks: Sequence[MicroChunk]) -> None:
    debug_dir = _debug_dir()
    safe_doc_id = _sanitize_doc_id(doc_id)
    outfile = debug_dir / f"{safe_doc_id}.jsonl"
    with outfile.open("w", encoding="utf-8") as handle:
        for chunk in microchunks:
            handle.write(json.dumps(dict(chunk), ensure_ascii=False) + "\n")


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
    token_size: int = 90,
    overlap: int = 12,
) -> StageBuildResult:
    """Return a stage payload extended with UF microchunks and section groups.

    The defaults mirror the UF specification (≤90 token windows with ~12 token
    overlap) so that stage builds are consistent with the end-to-end pipeline.
    """

    enriched_chunks: List[Dict[str, object]] = []
    for chunk in stage_chunks:
        part = dict(chunk)
        part["doc_id"] = doc_id
        enriched_chunks.append(part)

    microchunks = microchunk_text(enriched_chunks, size=token_size, overlap=overlap)
    _write_microchunk_debug(doc_id, microchunks)
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
