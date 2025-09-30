"""Upload routes."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..config import get_settings
from ..services.upload_service import NormalizedDoc, ensure_normalized
from ..services.upload_service.packages.storage import persist_upload_file
from ..util.errors import AppError, NotFoundError, ValidationError

router = APIRouter(prefix="/upload", tags=["upload"])


class UploadRequest(BaseModel):
    """Request payload for normalization."""

    file_id: str | None = None
    file_name: str | None = None


@router.post("/normalize", response_model=NormalizedDoc)
async def normalize_upload(request: UploadRequest) -> NormalizedDoc:
    """Normalize an uploaded file via manifest lookup or local path."""
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


@router.post("/normalize/file", response_model=NormalizedDoc)
async def normalize_uploaded_file(
    file: UploadFile = File(...), file_id: str | None = Form(None)
) -> NormalizedDoc:
    """Persist and normalize a multipart upload."""

    settings = get_settings()
    max_bytes = int(settings.upload_max_size_mb) * 1024 * 1024
    try:
        stored = await persist_upload_file(file, max_bytes=max_bytes)
        return await run_in_threadpool(
            ensure_normalized,
            file_id,
            stored.original_filename,
            stored,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AppError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
