"""Semantic labeling utilities."""

from __future__ import annotations

from typing import Any


def infer_semantics(
    text_blocks: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    images: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Label blocks by semantic role."""
    table_pages: set[int] = {table.get("page", 0) for table in tables}
    image_pages: set[int] = {image.get("page", 0) for image in images}
    semantics: list[dict[str, Any]] = []
    for block in text_blocks:
        text = block.get("text", "").strip()
        page = int(block.get("page", 0))
        role = "paragraph"
        confidence = 0.6
        if not text:
            role = "empty"
            confidence = 0.2
        elif text.isupper() and len(text) < 80:
            role = "heading"
            confidence = 0.85
        elif text.endswith(":"):
            role = "heading"
            confidence = 0.7
        elif text.startswith(("-", "*")):
            role = "list_item"
            confidence = 0.75
        elif page in table_pages:
            role = "table_context"
            confidence = 0.55
        elif page in image_pages and len(text) < 120:
            role = "caption"
            confidence = 0.65
        semantics.append(
            {
                "id": block.get("id"),
                "role": role,
                "confidence": round(confidence, 2),
            }
        )
    return semantics
