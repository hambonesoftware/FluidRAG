"""OCR routing utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def maybe_ocr(
    normalize_artifact_path: str, text_blocks: list[dict[str, Any]]
) -> dict[str, Any]:
    """Decide OCR & provide tokens layer."""
    normalized: dict[str, Any] = {}
    path = Path(normalize_artifact_path)
    if path.exists():
        try:
            normalized = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            normalized = {}
    stats = normalized.get("stats", {})
    performed = bool(stats.get("ocr_performed", False))
    coverage = float(stats.get("avg_coverage", 0.0))
    if not performed and coverage >= 0.85:
        return {"performed": False, "tokens": []}

    tokens: list[dict[str, Any]] = []
    for block in text_blocks:
        tokens.append(
            {
                "id": block.get("id"),
                "text": block.get("text", ""),
                "confidence": float(block.get("confidence", 0.0)),
            }
        )
    return {"performed": performed, "tokens": tokens}
