"""Upload routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..services.upload_service import NormalizedDoc, ensure_normalized
from ..util.errors import AppError, NotFoundError, ValidationError

router = APIRouter(prefix="/upload", tags=["upload"])


class UploadRequest(BaseModel):
    """Request payload for normalization."""

    file_id: str | None = None
    file_name: str | None = None


@router.post("/normalize", response_model=NormalizedDoc)
async def normalize_upload(request: UploadRequest) -> NormalizedDoc:
    """Normalize an uploaded file and return artifact metadata."""
    try:
        return await run_in_threadpool(
            ensure_normalized, request.file_id, request.file_name
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AppError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
