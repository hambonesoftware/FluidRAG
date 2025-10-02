"""Tests for parser fan-out/fan-in pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ...config import get_settings
from ...services.parser_service import ParseResult, parse_and_enrich
from ...services.upload_service import ensure_normalized
from ...util.errors import NotFoundError


def _parse_fixture(sample_pdf_path: Path) -> ParseResult:
    normalized = ensure_normalized(file_name=str(sample_pdf_path))
    return parse_and_enrich(normalized.doc_id, normalized.normalized_path)


def _write_and_normalize(tmp_path: Path, text: str) -> ParseResult:
    source = tmp_path / "sample.txt"
    source.write_text(text, encoding="utf-8")
    normalized = ensure_normalized(file_name=str(source))
    return parse_and_enrich(normalized.doc_id, normalized.normalized_path)


def test_parse_and_enrich_generates_enriched_artifact(sample_pdf_path: Path) -> None:
    result = _parse_fixture(sample_pdf_path)
    enriched_path = Path(result.enriched_path)
    assert enriched_path.exists()

    payload = json.loads(enriched_path.read_text(encoding="utf-8"))
    assert payload["language"]["code"] in {"en", "und"}
    assert payload["summary"]["block_count"] >= 6
    assert len(payload["reading_order"]) == len(payload["blocks"])
    assert payload["lists"], "list detection should capture bullet points"
    assert any(block["text"].startswith("2. Controls") for block in payload["blocks"])

    report_path = Path(result.report_path)
    assert report_path.exists()
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_payload["doc_id"] == result.doc_id
    assert report_payload["summary"] == result.summary


def test_parse_and_enrich_missing_normalized(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError):
        parse_and_enrich("missing", str(tmp_path / "does-not-exist.json"))


def test_parse_and_enrich_triggers_ocr(tmp_path: Path) -> None:
    text = "[image:scan]\n\n"
    get_settings.cache_clear()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("UPLOAD_OCR_THRESHOLD", "0.95")
    try:
        get_settings.cache_clear()
        result = _write_and_normalize(tmp_path, text)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
    payload = json.loads(Path(result.enriched_path).read_text(encoding="utf-8"))
    assert payload["ocr"]["performed"] is True
