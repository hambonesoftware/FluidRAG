"""Routes for retrieving pass artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..util.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/passes", tags=["passes"])


def _passes_dir(doc_id: str) -> Path:
    settings = get_settings()
    return Path(settings.artifact_root_path) / doc_id / "passes"


@router.get("/{doc_id}", response_model=dict)
async def list_passes(doc_id: str) -> dict:
    """Return manifest of generated passes for *doc_id*."""

    manifest_path = _passes_dir(doc_id) / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="pass manifest missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {"doc_id": doc_id, "passes": manifest.get("passes", {})}


@router.get("/{doc_id}/{pass_name}", response_model=dict)
async def get_pass(doc_id: str, pass_name: str) -> dict:
    """Return persisted pass payload."""

    manifest = await list_passes(doc_id)
    passes = manifest.get("passes", {})
    if pass_name not in passes:
        raise HTTPException(status_code=404, detail="pass not found")
    candidate = Path(passes[pass_name])
    if not candidate.is_absolute():
        candidate = _passes_dir(doc_id) / candidate.name
    if not candidate.exists():
        logger.warning("passes.get_missing", extra={"path": str(candidate)})
        raise HTTPException(status_code=404, detail="pass artifact missing")
    return json.loads(candidate.read_text(encoding="utf-8"))


__all__ = ["list_passes", "get_pass"]
