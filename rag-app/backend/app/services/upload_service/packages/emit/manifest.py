"""Manifest helpers for normalized artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_manifest(doc_id: str, artifact_path: str, kind: str) -> dict[str, Any]:
    """Emit artifact manifest with checksum."""
    target = Path(artifact_path)
    payload = target.read_bytes() if target.exists() else b""
    checksum = hashlib.sha256(payload).hexdigest()
    manifest = {
        "doc_id": doc_id,
        "artifact_path": str(target),
        "kind": kind,
        "checksum": checksum,
        "size": len(payload),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    manifest_path = target.with_name(f"{target.stem}.{kind}.manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest["manifest_path"] = str(manifest_path)
    return manifest
