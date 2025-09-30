"""Upload routes."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..services.upload_service import NormalizedDoc, ensure_normalized
from ..util.errors import AppError, NotFoundError, ValidationError
from ..util.logging import get_logger

router = APIRouter(prefix="/upload", tags=["upload"])

logger = get_logger(__name__)


class UploadRequest(BaseModel):
    """Request payload for normalization."""

    file_id: str | None = None
    file_name: str | None = None


@router.post("/normalize", response_model=NormalizedDoc)
async def normalize_upload(request: UploadRequest) -> NormalizedDoc:
    """Normalize an uploaded file and return artifact metadata."""
    try:
        logger.info(
            "route.upload.normalize", extra={"file_id": request.file_id, "file_name": request.file_name}
        )
        return await run_in_threadpool(
            ensure_normalized, request.file_id, request.file_name
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AppError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/pdf", response_model=NormalizedDoc)
async def upload_pdf(file: UploadFile = File(...)) -> NormalizedDoc:
    """Accept a raw PDF upload and process it via the upload service."""

    try:
        filename = file.filename or "uploaded.pdf"
        logger.info("route.upload.pdf", extra={"upload_filename": filename})
        payload = await file.read()
        return await run_in_threadpool(
            ensure_normalized,
            None,
            None,
            upload_bytes=payload,
            upload_filename=filename,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AppError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
