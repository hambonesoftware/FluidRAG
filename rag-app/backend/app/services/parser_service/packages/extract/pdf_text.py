"""Text extraction helpers."""

from __future__ import annotations

from typing import Any


def extract_text_blocks(normalized: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract text blocks with bbox/font."""
    blocks: list[dict[str, Any]] = []
    for page in normalized.get("pages", []):
        page_number = page.get("page_number", 0)
        for block in page.get("blocks", []):
            record = {
                "id": block.get("id"),
                "page": page_number,
                "text": block.get("text", ""),
                "bbox": block.get("bbox", [0.0, 0.0, 1.0, 1.0]),
                "font": block.get("font", {}),
                "confidence": float(block.get("confidence", 0.0)),
            }
            blocks.append(record)
    return blocks
