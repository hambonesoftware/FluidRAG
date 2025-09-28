"""Chunk service."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel

from backend.app.contracts.chunking import Chunk, ChunkCollection

from .chunk_controller import ChunkInternal, run_uf_chunking as controller_run


class ChunkResult(BaseModel):
    doc_id: str
    chunks: List[Chunk]
    embeddings: dict[str, list[float]]

    def to_contract(self) -> ChunkCollection:
        return ChunkCollection(doc_id=self.doc_id, chunks=self.chunks)


def run_uf_chunking(doc_id: str, normalize_artifact: str) -> ChunkResult:
    internal: ChunkInternal = controller_run(doc_id=doc_id, normalize_artifact=normalize_artifact)
    return ChunkResult(doc_id=internal.doc_id, chunks=internal.chunks, embeddings=internal.embeddings)
