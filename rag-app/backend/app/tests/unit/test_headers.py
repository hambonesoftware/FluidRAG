import json
from pathlib import Path

import pytest

from ...config import get_settings
from ...services.chunk_service import run_uf_chunking
from ...services.header_service import HeaderJoinResult, join_and_rechunk
from ...services.header_service.packages.repair.sequence import repair_sequence
from ...services.parser_service import parse_and_enrich
from ...services.upload_service import ensure_normalized

pytestmark = pytest.mark.phase5


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUIDRAG_OFFLINE", "true")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("CHUNK_TARGET_TOKENS", "18")
    monkeypatch.setenv("CHUNK_TOKEN_OVERLAP", "6")
    get_settings.cache_clear()


def _build_pipeline(tmp_path: Path, text: str) -> tuple[str, str]:
    source = tmp_path / "doc.txt"
    source.write_text(text, encoding="utf-8")
    normalized = ensure_normalized(file_name=str(source))
    parsed = parse_and_enrich(normalized.doc_id, normalized.normalized_path)
    chunks = run_uf_chunking(parsed.doc_id, parsed.enriched_path)
    return parsed.doc_id, chunks.chunks_path


def test_test_headers(tmp_path: Path) -> None:
    """End-to-end header join writes artifacts and section map."""

    doc_id, chunks_path = _build_pipeline(
        tmp_path,
        (
            "Executive Summary\nKey metrics overview for leadership.\n\n"
            "1. Introduction\nBaseline context for the reader.\n\n"
            "1.1 Scope\nBoundaries of the initiative.\n\n"
            "1.2 Background\nLegacy insights and dependencies.\n\n"
            "2. Results\nPrimary outcomes and KPIs.\n\n"
            "Appendix A – Tables\nSupporting quantitative tables."
        ),
    )

    result: HeaderJoinResult = join_and_rechunk(doc_id, chunks_path)

    headers_path = Path(result.headers_path)
    section_map_path = Path(result.section_map_path)
    header_chunks_path = Path(result.header_chunks_path)

    assert headers_path.exists(), "headers.json should be emitted"
    assert section_map_path.exists(), "section_map.json should be emitted"
    assert header_chunks_path.exists(), "header_chunks.jsonl should be emitted"

    headers_payload = json.loads(headers_path.read_text(encoding="utf-8"))
    assert headers_payload, "at least one header must be detected"
    intro_header = next(
        (row for row in headers_payload if row["text"].startswith("1. Introduction")),
        None,
    )
    assert intro_header is not None, "numbered headings should survive the pipeline"
    assert result.header_count == len(headers_payload)

    section_map = json.loads(section_map_path.read_text(encoding="utf-8"))
    assert section_map, "section map should map chunks to headers"
    mapped_headers = {row["header_id"] for row in section_map}
    all_headers = {row["header_id"] for row in headers_payload}
    assert mapped_headers <= all_headers
    assert mapped_headers, "at least one header should own chunk content"

    lines = [
        line
        for line in header_chunks_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(lines) == result.header_count
    for row in lines:
        payload = json.loads(row)
        assert payload["text"].strip(), "header chunks must include aggregated text"
        assert payload["header_text"], "header text should be preserved in aggregation"


def test_sequence_repair_recovers_missing_headers() -> None:
    """Confirm A5/A6 hole repair using curated sample."""

    repaired = repair_sequence(
        [
            {
                "section_key": "appendix-a",
                "ordinal": 1,
                "chunk_index": 0,
                "score": 0.82,
                "text": "Appendix A.1 Overview",
                "sentence_start": 0,
                "sentence_end": 0,
                "chunk_ids": ["c1"],
            },
            {
                "section_key": "appendix-a",
                "ordinal": 3,
                "chunk_index": 3,
                "score": 0.81,
                "text": "Appendix A.3 Findings",
                "sentence_start": 6,
                "sentence_end": 6,
                "chunk_ids": ["c3"],
            },
            {
                "section_key": "appendix-a",
                "ordinal": 2,
                "chunk_index": 2,
                "score": 0.41,
                "text": "Appendix A.2 Methodology",
                "sentence_start": 4,
                "sentence_end": 4,
                "chunk_ids": ["c2"],
            },
        ]
    )

    ordinals = [
        row.get("ordinal") for row in repaired if row.get("section_key") == "appendix-a"
    ]
    assert ordinals == [1, 2, 3]
    recovered = next(row for row in repaired if row.get("ordinal") == 2)
    assert recovered.get(
        "recovered", True
    ), "sequence repair should promote missing ordinal"
    assert recovered.get("score", 0) >= 0.35
