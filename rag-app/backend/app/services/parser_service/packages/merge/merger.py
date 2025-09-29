"""Merge helpers for parser output."""

from __future__ import annotations

from typing import Any


def merge_all(
    doc_id: str,
    language: dict[str, Any],
    text_blocks: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    images: list[dict[str, Any]],
    links: list[dict[str, Any]],
    ocr_layer: dict[str, Any],
    reading_order: list[int],
    semantics: list[dict[str, Any]],
    lists: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge parsing facets into a single enriched artifact."""
    summary = {
        "doc_id": doc_id,
        "language": language,
        "block_count": len(text_blocks),
        "table_count": len(tables),
        "image_count": len(images),
        "link_count": len(links),
        "list_count": len(lists),
    }
    return {
        "doc_id": doc_id,
        "language": language,
        "blocks": text_blocks,
        "tables": tables,
        "images": images,
        "links": links,
        "ocr": ocr_layer,
        "reading_order": reading_order,
        "semantics": semantics,
        "lists": lists,
        "summary": summary,
    }
