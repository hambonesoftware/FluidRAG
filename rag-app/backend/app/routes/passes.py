"""RAG passes routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..services.rag_pass_service import run_all
from ..util.errors import AppError

router = APIRouter(prefix="/passes", tags=["passes"])


class PassesPayload(BaseModel):
    doc_id: str
    rechunk_artifact: str


@router.post("/")
def passes_entry(payload: PassesPayload) -> Any:
    try:
        result = run_all(doc_id=payload.doc_id, rechunk_artifact=payload.rechunk_artifact)
        return {"doc_id": result.doc_id, "passes": len(result.passes)}
    except Exception as exc:
        if isinstance(exc, AppError):
            raise
        raise AppError(str(exc)) from exc
