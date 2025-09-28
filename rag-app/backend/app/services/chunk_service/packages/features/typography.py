"""Typography feature extraction for chunking."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .....util.logging import get_logger

logger = get_logger(__name__)


def _extract_font(block: dict[str, Any]) -> dict[str, Any]:
    font = block.get("font")
    if isinstance(font, dict):
        return font
    style = block.get("style")
    if isinstance(style, dict):
        candidate = style.get("font")
        if isinstance(candidate, dict):
            return candidate
    return {}


def _is_heading(text: str, font: dict[str, Any]) -> bool:
    if not text:
        return False
    upper_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    size = float(font.get("size", 0) or 0)
    weight = str(font.get("weight", "")).lower()
    return size >= 16 or (upper_ratio > 0.55 and weight in {"bold", "700"})


def extract_typography(normalize_artifact_path: str | None = None) -> dict[str, Any]:
    """Compute typography features."""
    if not normalize_artifact_path:
        return {}
    path = Path(normalize_artifact_path)
    if not path.exists():
        logger.warning(
            "chunk.typography.missing_artifact", extra={"path": normalize_artifact_path}
        )
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error(
            "chunk.typography.invalid_json",
            extra={"path": normalize_artifact_path, "error": str(exc)},
        )
        return {}

    features: dict[str, Any] = {"pages": {}, "headings": []}
    total_size = 0.0
    total_weight = 0.0
    block_count = 0
    for page in payload.get("pages", []):
        page_number = page.get("page_number")
        sizes: list[float] = []
        for block in page.get("blocks", []):
            font = _extract_font(block)
            size = float(font.get("size", 0) or 0)
            weight = font.get("weight", "normal")
            sizes.append(size)
            total_size += size
            total_weight += 700.0 if str(weight).lower() in {"bold", "700"} else 400.0
            block_count += 1
            if _is_heading(block.get("text", ""), font):
                features.setdefault("headings", []).append(block.get("id"))
        if sizes:
            features["pages"][str(page_number or len(features["pages"]) + 1)] = {
                "avg_size": sum(sizes) / len(sizes),
                "max_size": max(sizes),
                "min_size": min(sizes),
            }
    if block_count:
        features["avg_size"] = total_size / block_count
        features["avg_weight"] = total_weight / block_count
    else:
        features["avg_size"] = 0.0
        features["avg_weight"] = 0.0
    return features
