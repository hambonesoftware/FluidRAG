"""Parser routes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..contracts.ingest import NormalizedText
from ..services.parser_service import parse_and_enrich
from ..util.errors import AppError

router = APIRouter(prefix="/parser", tags=["parser"])


class ParserPayload(BaseModel):
    doc_id: str
    manifest: str


@router.post("/")
def parser_entry(payload: ParserPayload) -> Any:
    try:
        manifest = json.loads(Path(payload.manifest).read_text(encoding="utf-8"))
        normalized = NormalizedText(
            doc_id=payload.doc_id,
            text="\n\n".join(manifest.get("pages", [])),
            pages=manifest.get("pages", []),
            meta=manifest.get("meta", {}),
        )
        result = parse_and_enrich(normalized)
        return {"doc_id": result.doc_id, "texts": len(result.document.texts)}
    except Exception as exc:
        if isinstance(exc, AppError):
            raise
        raise AppError(str(exc)) from exc
