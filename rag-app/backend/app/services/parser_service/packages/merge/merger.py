"""Merge parser artifacts."""
from __future__ import annotations

from typing import Dict, List

from backend.app.contracts.parsing import ImageBlock, LinkBlock, ParsedDocument, TableBlock, TextBlock


def merge_all(
    *,
    doc_id: str,
    texts: List[TextBlock],
    tables: List[TableBlock],
    images: List[ImageBlock],
    links: List[LinkBlock],
    meta: Dict[str, str],
) -> ParsedDocument:
    return ParsedDocument(doc_id=doc_id, texts=texts, tables=tables, images=images, links=links, meta=meta)
