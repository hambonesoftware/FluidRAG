"""Lightweight persistence helpers for pipeline manifests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..util.logging import get_logger
from .storage import ensure_parent_dirs, write_json

logger = get_logger(__name__)


def upsert_document_record(
    doc_id: str, normalize_path: str, manifest: dict[str, Any]
) -> None:
    """Upsert doc record in persistence store."""

    if not doc_id or not doc_id.strip():
        raise ValueError("doc_id is required")
    settings = get_settings()
    doc_root = Path(settings.artifact_root_path) / doc_id
    doc_root.mkdir(parents=True, exist_ok=True)
    record_path = doc_root / "document.manifest.json"
    payload = {
        "doc_id": doc_id,
        "normalized_artifact": normalize_path,
        "manifest": manifest,
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    ensure_parent_dirs(str(record_path))
    write_json(str(record_path), payload)
    logger.info("db.upsert_document_record", extra={"doc_id": doc_id})


__all__ = ["upsert_document_record"]
