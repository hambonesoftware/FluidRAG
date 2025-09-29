"""Routes for retrieving pass artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..util.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/passes", tags=["passes"])


def _passes_dir(doc_id: str) -> Path:
    settings = get_settings()
    return Path(settings.artifact_root_path) / doc_id / "passes"


@router.get("/{doc_id}", response_model=dict[str, Any])
async def list_passes(doc_id: str) -> dict[str, Any]:
    """Return manifest of generated passes for *doc_id*."""

    manifest_path = _passes_dir(doc_id) / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="pass manifest missing")
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest_data, dict):
        logger.error(
            "passes.manifest_invalid",
            extra={"doc_id": doc_id, "path": str(manifest_path)},
        )
        raise HTTPException(status_code=500, detail="invalid pass manifest")
    passes = manifest_data.get("passes", {})
    if not isinstance(passes, dict):
        passes = {}
    typed_passes: dict[str, str] = {}
    for name, value in passes.items():
        if isinstance(name, str) and isinstance(value, str):
            typed_passes[name] = value
    return {"doc_id": doc_id, "passes": typed_passes}


@router.get("/{doc_id}/{pass_name}", response_model=dict[str, Any])
async def get_pass(doc_id: str, pass_name: str) -> dict[str, Any]:
    """Return persisted pass payload."""

    manifest = await list_passes(doc_id)
    passes = manifest.get("passes", {})
    if not isinstance(passes, dict):
        passes = {}
    if pass_name not in passes:
        raise HTTPException(status_code=404, detail="pass not found")
    candidate_path = passes.get(pass_name)
    if not isinstance(candidate_path, str):
        raise HTTPException(status_code=500, detail="invalid pass manifest entry")
    candidate = Path(candidate_path)
    if not candidate.is_absolute():
        candidate = _passes_dir(doc_id) / candidate.name
    if not candidate.exists():
        logger.warning("passes.get_missing", extra={"path": str(candidate)})
        raise HTTPException(status_code=404, detail="pass artifact missing")
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    logger.error(
        "passes.payload_invalid", extra={"doc_id": doc_id, "path": str(candidate)}
    )
    raise HTTPException(status_code=500, detail="invalid pass payload")


__all__ = ["list_passes", "get_pass"]
