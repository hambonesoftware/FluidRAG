"""Tests for parser fan-out/fan-in pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ...config import get_settings
from ...services.parser_service import ParseResult, parse_and_enrich
from ...services.upload_service import ensure_normalized
from ...util.errors import NotFoundError


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUIDRAG_OFFLINE", "true")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("UPLOAD_OCR_THRESHOLD", "0.9")
    monkeypatch.setenv("PARSER_TIMEOUT_SECONDS", "1.5")
    get_settings.cache_clear()


def _write_and_normalize(tmp_path: Path, text: str) -> ParseResult:
    source = tmp_path / "sample.txt"
    source.write_text(text, encoding="utf-8")
    normalized = ensure_normalized(file_name=str(source))
    return parse_and_enrich(normalized.doc_id, normalized.normalized_path)


def test_parse_and_enrich_generates_enriched_artifact(tmp_path: Path) -> None:
    text = (
        "INTRODUCTION\n\n"
        "- bullet one\n"
        "- bullet two\n\n"
        "Table\nA|B\n1|2\n\n"
        "[image:diagram]\n\n"
        "See https://example.com"
    )
    result = _write_and_normalize(tmp_path, text)
    enriched_path = Path(result.enriched_path)
    assert enriched_path.exists()

    payload = json.loads(enriched_path.read_text(encoding="utf-8"))
    assert payload["language"]["code"] in {"en", "und"}
    assert payload["summary"]["block_count"] >= 2
    assert len(payload["reading_order"]) == len(payload["blocks"])
    assert payload["lists"], "list detection should capture bullet points"


def test_parse_and_enrich_missing_normalized(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError):
        parse_and_enrich("missing", str(tmp_path / "does-not-exist.json"))


def test_parse_and_enrich_triggers_ocr(tmp_path: Path) -> None:
    text = "[image:scan]\n\n"
    result = _write_and_normalize(tmp_path, text)
    payload = json.loads(Path(result.enriched_path).read_text(encoding="utf-8"))
    assert payload["ocr"]["performed"] is True
