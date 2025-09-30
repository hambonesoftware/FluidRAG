"""Document status and results routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services.upload_service import (
    get_document_headers,
    get_document_status,
)
from ..util.errors import NotFoundError
from ..util.logging import get_logger

router = APIRouter(prefix="/api/docs", tags=["docs"])

logger = get_logger(__name__)


@router.get("/{doc_id}")
async def get_doc_status(doc_id: str) -> dict[str, object]:
    """Return upload and parser status for *doc_id*."""

    logger.info("route.docs.status", extra={"doc_id": doc_id})
    try:
        return get_document_status(doc_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{doc_id}/headers")
async def get_doc_headers(doc_id: str) -> dict[str, object]:
    """Return headers tree artifact for *doc_id*."""

    logger.info("route.docs.headers", extra={"doc_id": doc_id})
    try:
        return get_document_headers(doc_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

