"""Upload routes."""
from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.upload_service import ensure_normalized
from ..util.errors import AppError

router = APIRouter(prefix="/upload", tags=["upload"])


class UploadPayload(BaseModel):
    file_name: str
    content: str
    content_type: str = "application/pdf"


@router.post("/")
def upload_file(payload: UploadPayload) -> Any:
    try:
        content = base64.b64decode(payload.content.encode("utf-8"))
        normalized = ensure_normalized(
            file_name=payload.file_name,
            content=content,
            content_type=payload.content_type,
        )
        return {"doc_id": normalized.doc_id, "manifest": normalized.manifest_path}
    except Exception as exc:
        if isinstance(exc, AppError):
            raise
        raise AppError(str(exc)) from exc
