"""Parser routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..services.parser_service import ParseResult, parse_and_enrich
from ..util.errors import AppError, NotFoundError, ValidationError

router = APIRouter(prefix="/parser", tags=["parser"])


class ParserRequest(BaseModel):
    """Request body for parser enrichment."""

    doc_id: str
    normalize_artifact: str


@router.post("/enrich", response_model=ParseResult)
async def enrich_document(request: ParserRequest) -> ParseResult:
    """Run parser fan-out/fan-in pipeline."""
    try:
        return await run_in_threadpool(
            parse_and_enrich, request.doc_id, request.normalize_artifact
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AppError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
