"""Header routes."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.header_service import join_and_rechunk
from ..util.errors import AppError

router = APIRouter(prefix="/headers", tags=["headers"])


class HeaderPayload(BaseModel):
    doc_id: str
    chunks_artifact: str


@router.post("/")
def headers_entry(payload: HeaderPayload) -> Any:
    try:
        result = join_and_rechunk(doc_id=payload.doc_id, chunks_artifact=payload.chunks_artifact)
        base_dir = Path(payload.chunks_artifact).parent
        return {
            "doc_id": result.doc_id,
            "headers": len(result.headers),
            "rechunk_artifact": str(base_dir / "headers.json"),
        }
    except Exception as exc:
        if isinstance(exc, AppError):
            raise
        raise AppError(str(exc)) from exc
