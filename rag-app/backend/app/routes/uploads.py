"""Upload API routes implementing final stubs contract."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool

from ..services.upload_service import (
    UploadResponse,
    handle_upload,
)
from ..util.errors import NotFoundError, ValidationError
from ..util.logging import get_logger

router = APIRouter(prefix="/api", tags=["uploads"])

logger = get_logger(__name__)


@router.post("/uploads", response_model=UploadResponse, status_code=201)
async def post_upload(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    doc_label: str | None = Form(None),
    project_id: str | None = Form(None),
) -> UploadResponse:
    """Handle multipart uploads with validation and parser kick-off."""

    request_id = getattr(request.state, "request_id", None)
    client_ip = request.client.host if request.client else None
    filename = file.filename or "document.pdf"
    logger.info(
        "route.uploads.post",
        extra={
            "request_id": request_id,
            "filename": filename,
            "doc_label": doc_label,
            "project_id": project_id,
            "client_ip": client_ip,
        },
    )
    try:
        upload_response = await run_in_threadpool(
            handle_upload,
            stream=file.file,
            filename=filename,
            doc_label=doc_label,
            project_id=project_id,
            request_id=request_id,
            client_ip=client_ip,
        )
    except ValidationError as exc:
        status_code = getattr(exc, "status_code", 400)
        detail = getattr(exc, "code", None) or str(exc)
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except NotFoundError as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if getattr(upload_response, "duplicate", False):
        response.status_code = 200
        logger.info(
            "route.uploads.duplicate", extra={"doc_id": upload_response.doc_id}
        )
    return upload_response
