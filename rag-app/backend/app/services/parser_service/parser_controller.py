"""Parser controller orchestrating detection/extraction/enhancement."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from backend.app.contracts.ingest import NormalizedText
from backend.app.contracts.parsing import ParsedDocument
from backend.app.util.errors import AppError

from .packages.enhance.lists_bullets import detect_lists_bullets
from .packages.enhance.reading_order import build_reading_order
from .packages.enhance.semantics import infer_semantics
from .packages.extract.images import extract_images
from .packages.extract.links import extract_links
from .packages.extract.pdf_text import extract_text_blocks
from .packages.extract.tables import extract_tables
from .packages.merge.merger import merge_all


@dataclass(slots=True)
class ParseInternal:
    doc_id: str
    document: ParsedDocument
    annotations: Dict[str, Dict[int, str]]


def parse_and_enrich(normalized: NormalizedText) -> ParseInternal:
    text_blocks = extract_text_blocks(normalized.doc_id, normalized.pages)
    tables = extract_tables(normalized.pages)
    images = extract_images(normalized.pages)
    links = extract_links(normalized.pages)

    ordered_blocks = build_reading_order(text_blocks)
    semantics = infer_semantics(ordered_blocks)
    lists = detect_lists_bullets(ordered_blocks)

    annotations = {"semantics": semantics, "lists": {idx: str(flag) for idx, flag in lists.items()}}
    doc = merge_all(doc_id=normalized.doc_id, texts=ordered_blocks, tables=tables, images=images, links=links, meta=normalized.meta)
    return ParseInternal(doc_id=normalized.doc_id, document=doc, annotations=annotations)


def handle_parser_errors(exc: Exception) -> Dict[str, str]:
    if isinstance(exc, AppError):
        return exc.to_dict()
    return {"message": str(exc), "type": exc.__class__.__name__}
