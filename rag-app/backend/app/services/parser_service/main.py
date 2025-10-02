"""Parser service public API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .parser_controller import ParseInternal
from .parser_controller import parse_and_enrich as controller_parse_and_enrich


class ParseResult(BaseModel):
    """Parser enriched artifact."""

    doc_id: str
    enriched_path: str
    report_path: str | None = Field(default=None)
    language: str = Field(default="und", min_length=2)
    summary: dict[str, object] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)


def parse_and_enrich(doc_id: str, normalize_artifact: str) -> ParseResult:
    """Fan-out/fan-in parser; returns enriched parse path."""
    internal: ParseInternal = controller_parse_and_enrich(
        doc_id=doc_id, normalize_artifact=normalize_artifact
    )
    return ParseResult(**internal.model_dump())


__all__ = ["ParseResult", "parse_and_enrich"]
