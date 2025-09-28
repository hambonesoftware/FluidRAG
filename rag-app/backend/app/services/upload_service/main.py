"""Upload service public API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .upload_controller import NormalizedDocInternal
from .upload_controller import ensure_normalized as controller_ensure_normalized


class NormalizedDoc(BaseModel):
    """Normalized document artifact."""

    doc_id: str
    normalized_path: str
    manifest_path: str
    avg_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    block_count: int = 0
    ocr_performed: bool = False


def ensure_normalized(
    file_id: str | None = None, file_name: str | None = None
) -> NormalizedDoc:
    """Validate/normalize upload and emit normalize.json."""
    internal: NormalizedDocInternal = controller_ensure_normalized(
        file_id=file_id, file_name=file_name
    )
    return NormalizedDoc(**internal.model_dump())


__all__ = ["NormalizedDoc", "ensure_normalized"]
