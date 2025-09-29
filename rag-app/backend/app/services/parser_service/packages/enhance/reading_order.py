"""Reading order heuristics."""

from __future__ import annotations

from typing import Any


def _sort_key(block: dict[str, Any]) -> tuple[int, float, float, str]:
    bbox = block.get("bbox", [0.0, 0.0, 1.0, 1.0])
    return (
        int(block.get("page", 0)),
        float(bbox[1]) if len(bbox) > 1 else 0.0,
        float(bbox[0]) if bbox else 0.0,
        block.get("id", ""),
    )


def build_reading_order(
    text_blocks: list[dict[str, Any]],
    ocr_layer: dict[str, Any],
    images: list[dict[str, Any]],
) -> list[int]:
    """Compute reading order for blocks."""
    indexed = list(enumerate(text_blocks))
    indexed.sort(key=lambda item: _sort_key(item[1]))
    return [index for index, _ in indexed]
