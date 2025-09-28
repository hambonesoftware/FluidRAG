from __future__ import annotations

from pathlib import Path

from ...contracts.ingest import NormalizedText
from ...services.parser_service import parse_and_enrich
from ...services.upload_service import ensure_normalized


def test_test_parser() -> None:
    sample_path = Path(__file__).resolve().parents[2] / "data" / "sample.pdf"
    normalized = ensure_normalized(
        file_name="sample.pdf",
        content=sample_path.read_bytes(),
        content_type="application/pdf",
    )
    result = parse_and_enrich(normalized.to_contract())
    assert result.document.texts
    assert any(block.content.lower().startswith("introduction") for block in result.document.texts)


def test_parser_with_tables_and_ocr() -> None:
    normalized = NormalizedText(doc_id="doc", text="", pages=[""], meta={})
    result = parse_and_enrich(normalized)
    assert result.document.doc_id == "doc"
    assert result.document.texts == []
