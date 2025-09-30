"""Upload service public API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.util.logging import get_logger

from .upload_controller import (
    NormalizedDocInternal,
    UploadResponseModel,
    ensure_normalized as controller_ensure_normalized,
    get_headers as controller_get_headers,
    get_status as controller_get_status,
    process_upload as controller_process_upload,
)


logger = get_logger(__name__)


class NormalizedDoc(BaseModel):
    """Normalized document artifact."""

    doc_id: str
    normalized_path: str
    manifest_path: str
    avg_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    block_count: int = 0
    ocr_performed: bool = False
    source_checksum: str = Field(min_length=1)
    source_bytes: int = Field(default=0, ge=0)
    source_path: str = Field(min_length=1)


def ensure_normalized(
    file_id: str | None = None,
    file_name: str | None = None,
    *,
    upload_bytes: bytes | None = None,
    upload_filename: str | None = None,
) -> NormalizedDoc:
    """Validate/normalize upload and emit normalize.json"""
    logger.info(
        "service.upload.ensure_normalized",
        extra={
            "file_id": file_id,
            "file_name": file_name,
            "upload_filename": upload_filename,
            "has_bytes": upload_bytes is not None,
        },
    )
    internal: NormalizedDocInternal = controller_ensure_normalized(
        file_id=file_id,
        file_name=file_name,
        upload_bytes=upload_bytes,
        upload_filename=upload_filename,
    )
    result = NormalizedDoc(**internal.model_dump())
    logger.info(
        "service.upload.ensure_normalized.success",
        extra={
            "doc_id": result.doc_id,
            "normalized_path": result.normalized_path,
            "manifest_path": result.manifest_path,
        },
    )
    return result


class UploadResponse(BaseModel):
    """API response model for direct uploads."""

    doc_id: str
    filename: str
    size_bytes: int
    sha256: str
    stored_path: str
    job_id: str | None = None
    duplicate: bool = Field(default=False, exclude=True)


def handle_upload(
    *,
    stream,
    filename: str,
    doc_label: str | None,
    project_id: str | None,
    request_id: str | None,
    client_ip: str | None,
) -> UploadResponse:
    """Delegate direct upload processing to controller."""

    logger.info(
        "service.upload.handle_upload",
        extra={
            "filename": filename,
            "doc_label": doc_label,
            "project_id": project_id,
            "request_id": request_id,
        },
    )
    response_model, duplicate = controller_process_upload(
        stream=stream,
        filename=filename,
        doc_label=doc_label,
        project_id=project_id,
        request_id=request_id,
        client_ip=client_ip,
    )
    response: UploadResponseModel = response_model
    result = UploadResponse(**response.model_dump(), duplicate=duplicate)
    logger.info(
        "service.upload.handle_upload.success",
        extra={
            "doc_id": result.doc_id,
            "filename": result.filename,
            "size_bytes": result.size_bytes,
            "sha256": result.sha256,
            "job_id": result.job_id,
            "duplicate": duplicate,
        },
    )
    return result


def get_document_status(doc_id: str) -> dict[str, Any]:
    """Return serialized document status payload."""

    record = controller_get_status(doc_id)
    payload = record.model_dump()
    payload["uploaded_at"] = record.uploaded_at.isoformat()
    payload["updated_at"] = record.updated_at.isoformat()
    return payload


def get_document_headers(doc_id: str) -> dict[str, Any]:
    """Return headers tree artifact."""

    return controller_get_headers(doc_id)


__all__ = [
    "NormalizedDoc",
    "ensure_normalized",
    "UploadResponse",
    "handle_upload",
    "get_document_status",
    "get_document_headers",
]
