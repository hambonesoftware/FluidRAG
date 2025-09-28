"""Chunk service facade."""

from __future__ import annotations

from pydantic import BaseModel

from .chunk_controller import ChunkInternal
from .chunk_controller import run_uf_chunking as controller_run_uf_chunking


class ChunkResult(BaseModel):
    """UF chunking result."""

    doc_id: str
    chunks_path: str
    chunk_count: int
    index_manifest_path: str | None = None


def run_uf_chunking(
    doc_id: str | None = None, normalize_artifact: str | None = None
) -> ChunkResult:
    """Create UF chunks from enriched parse."""
    internal: ChunkInternal = controller_run_uf_chunking(
        doc_id=doc_id, normalize_artifact=normalize_artifact
    )
    return ChunkResult(**internal.model_dump())


__all__ = ["ChunkResult", "run_uf_chunking"]
