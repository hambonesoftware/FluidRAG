"""Public parser service API."""
from __future__ import annotations

from dataclasses import dataclass

from backend.app.contracts.ingest import NormalizedText
from backend.app.contracts.parsing import ParsedDocument

from .parser_controller import ParseInternal, parse_and_enrich as controller_parse


@dataclass(slots=True)
class ParseResult:
    doc_id: str
    document: ParsedDocument


def parse_and_enrich(normalized: NormalizedText) -> ParseResult:
    internal: ParseInternal = controller_parse(normalized)
    return ParseResult(doc_id=internal.doc_id, document=internal.document)
