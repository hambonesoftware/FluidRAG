"""Chunk routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..services.chunk_service import ChunkResult, run_uf_chunking
from ..util.errors import AppError, NotFoundError, ValidationError

router = APIRouter(prefix="/chunk", tags=["chunk"])


class ChunkRequest(BaseModel):
    """Request body for chunk generation."""

    doc_id: str
    normalize_artifact: str


@router.post("/uf", response_model=ChunkResult)
async def chunk_document(request: ChunkRequest) -> ChunkResult:
    """Generate UF chunks and build local indexes."""
    try:
        return await run_in_threadpool(
            run_uf_chunking, request.doc_id, request.normalize_artifact
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AppError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
