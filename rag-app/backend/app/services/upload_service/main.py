"""Upload service public API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.util.logging import get_logger

from .upload_controller import NormalizedDocInternal
from .upload_controller import ensure_normalized as controller_ensure_normalized


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


__all__ = ["NormalizedDoc", "ensure_normalized"]
