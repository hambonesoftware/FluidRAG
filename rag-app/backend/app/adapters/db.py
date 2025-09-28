"""Lightweight persistence facade."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

from ..config import settings


def upsert_document_record(doc_id: str, payload: Dict[str, Any]) -> Path:
    db_path = settings.storage_dir / "db" / f"{doc_id}.json"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with db_path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2, sort_keys=True)
    return db_path
