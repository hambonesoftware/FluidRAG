"""Routes for header detection and section rechunking."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..services.header_service import HeaderJoinResult, join_and_rechunk
from ..util.errors import AppError, NotFoundError, ValidationError

router = APIRouter(prefix="/headers", tags=["headers"])


class HeaderJoinRequest(BaseModel):
    """Request body for header detection."""

    doc_id: str
    chunks_artifact: str


@router.post("/join", response_model=HeaderJoinResult)
async def join_headers(request: HeaderJoinRequest) -> HeaderJoinResult:
    """Detect headers, repair numbering, and emit section-aligned chunks."""
    try:
        return await run_in_threadpool(
            join_and_rechunk, request.doc_id, request.chunks_artifact
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AppError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


__all__ = ["router"]
