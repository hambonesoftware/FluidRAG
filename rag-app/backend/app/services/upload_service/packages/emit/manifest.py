"""Emit manifest files."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from backend.app.adapters.storage import storage


def write_manifest(doc_id: str, pages: List[str], meta: Dict[str, str]) -> Path:
    payload = {"doc_id": doc_id, "pages": pages, "meta": meta}
    return storage.write_json(f"{doc_id}/manifest.json", payload)
