"""Chunk routes."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.chunk_service import run_uf_chunking
from ..util.errors import AppError

router = APIRouter(prefix="/chunk", tags=["chunk"])


class ChunkPayload(BaseModel):
    doc_id: str
    manifest: str


@router.post("/")
def chunk_entry(payload: ChunkPayload) -> Any:
    try:
        result = run_uf_chunking(doc_id=payload.doc_id, normalize_artifact=payload.manifest)
        base_dir = Path(payload.manifest).parent
        return {
            "doc_id": result.doc_id,
            "chunks": len(result.chunks),
            "chunks_artifact": str(base_dir / "chunks.jsonl"),
        }
    except Exception as exc:
        if isinstance(exc, AppError):
            raise
        raise AppError(str(exc)) from exc
