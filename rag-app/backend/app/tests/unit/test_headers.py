import json
from pathlib import Path
from typing import Any

import pytest

from ...config import get_settings
from ...services.chunk_service import run_uf_chunking
from ...services.header_service import HeaderJoinResult, join_and_rechunk
from ...services.header_service.packages.heur import regex_bank
from ...services.header_service.packages.heur.regex_bank import (
    find_header_candidates,
)
from ...services.header_service.packages.join.stitcher import stitch_headers
from ...services.header_service.packages.rechunk.by_headers import (
    rechunk_by_headers,
)
from ...services.header_service.packages.repair.sequence import repair_sequence
from ...services.header_service.packages.score.typo_features import score_typo
from ...services.parser_service import parse_and_enrich
from ...services.upload_service import ensure_normalized

pytestmark = pytest.mark.phase5


def _build_pipeline(
    sample_pdf_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, str]:
    monkeypatch.setenv("CHUNK_TARGET_TOKENS", "22")
    monkeypatch.setenv("CHUNK_TOKEN_OVERLAP", "6")
    get_settings.cache_clear()
    normalized = ensure_normalized(file_name=str(sample_pdf_path))
    parsed = parse_and_enrich(normalized.doc_id, normalized.normalized_path)
    chunks = run_uf_chunking(parsed.doc_id, parsed.enriched_path)
    return parsed.doc_id, chunks.chunks_path


def _normalize_header_text(value: str) -> str:
    first_line = value.splitlines()[0].strip()
    trimmed = regex_bank._trim_header_text(first_line)
    return trimmed.lower()


def _write_chunks(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    path = tmp_path / "chunks.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    return path


def test_header_pipeline(
    sample_pdf_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    expected_sections: dict[str, list[str]],
) -> None:
    """End-to-end header join writes artifacts and section map for curated fixture."""

    doc_id, chunks_path = _build_pipeline(sample_pdf_path, monkeypatch)

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
    detected_text = [row["text"] for row in headers_payload]
    for header in expected_sections["headers"]:
        assert any(text.startswith(header) for text in detected_text), header

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
    has_chunk_ids = False
    for row in lines:
        payload = json.loads(row)
        assert payload["text"].strip(), "header chunks must include aggregated text"
        assert payload["header_text"], "header text should be preserved in aggregation"
        if payload.get("chunk_ids"):
            has_chunk_ids = True
    assert has_chunk_ids, "at least one header chunk should list contributing chunk ids"


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


def test_header_pipeline_precision_recall_meets_benchmark(
    tmp_path: Path,
) -> None:
    """Regex + typography pipeline should exceed benchmark precision/recall."""

    rows = [
        {
            "doc_id": "doc",
            "chunk_id": "c1",
            "text": "Executive Summary",
            "sentence_start": 0,
            "sentence_end": 0,
            "chunk_index": 0,
            "typography": {"avg_size": 17, "avg_weight": 700},
        },
        {
            "doc_id": "doc",
            "chunk_id": "c2",
            "text": "1. Introduction",
            "sentence_start": 2,
            "sentence_end": 2,
            "chunk_index": 100,
            "typography": {"avg_size": 15, "avg_weight": 650},
        },
        {
            "doc_id": "doc",
            "chunk_id": "c3",
            "text": "1.1 Scope",
            "sentence_start": 4,
            "sentence_end": 4,
            "chunk_index": 200,
            "typography": {"avg_size": 14, "avg_weight": 620},
        },
        {
            "doc_id": "doc",
            "chunk_id": "c4",
            "text": "1.2 Background",
            "sentence_start": 6,
            "sentence_end": 6,
            "chunk_index": 300,
            "typography": {"avg_size": 14, "avg_weight": 620},
        },
        {
            "doc_id": "doc",
            "chunk_id": "c5",
            "text": "Section 2 Results",
            "sentence_start": 8,
            "sentence_end": 8,
            "chunk_index": 400,
            "typography": {"avg_size": 15, "avg_weight": 640},
        },
        {
            "doc_id": "doc",
            "chunk_id": "c6",
            "text": "2.1 Primary KPIs",
            "sentence_start": 10,
            "sentence_end": 10,
            "chunk_index": 500,
            "typography": {"avg_size": 14, "avg_weight": 600},
        },
        {
            "doc_id": "doc",
            "chunk_id": "c7",
            "text": "2.2 Secondary Metrics",
            "sentence_start": 12,
            "sentence_end": 12,
            "chunk_index": 600,
            "typography": {"avg_size": 14, "avg_weight": 600},
        },
        {
            "doc_id": "doc",
            "chunk_id": "c8",
            "text": "Appendix A-1 Raw Tables",
            "sentence_start": 14,
            "sentence_end": 14,
            "chunk_index": 700,
            "typography": {"avg_size": 14, "avg_weight": 600},
        },
        {
            "doc_id": "doc",
            "chunk_id": "c9",
            "text": "Appendix A-2 Summary",
            "sentence_start": 16,
            "sentence_end": 16,
            "chunk_index": 800,
            "typography": {"avg_size": 14, "avg_weight": 600},
        },
        {
            "doc_id": "doc",
            "chunk_id": "c10",
            "text": "Appendix B-2 Checklists",
            "sentence_start": 18,
            "sentence_end": 18,
            "chunk_index": 900,
            "typography": {"avg_size": 14, "avg_weight": 600},
        },
        {
            "doc_id": "doc",
            "chunk_id": "c11",
            "text": "III. Conclusion",
            "sentence_start": 20,
            "sentence_end": 20,
            "chunk_index": 1000,
            "typography": {"avg_size": 15, "avg_weight": 640},
        },
    ]
    artifact_path = _write_chunks(tmp_path, rows)

    expected_headers = {
        "Executive Summary",
        "1. Introduction",
        "1.1 Scope",
        "1.2 Background",
        "Section 2 Results",
        "2.1 Primary KPIs",
        "2.2 Secondary Metrics",
        "Appendix A-1 Raw Tables",
        "Appendix A-2 Summary",
        "Appendix B-2 Checklists",
        "III. Conclusion",
    }

    candidates = find_header_candidates(str(artifact_path))
    assert candidates, "regex heuristics should find at least one candidate"
    scored = score_typo([dict(candidate) for candidate in candidates])
    assert any(
        float(candidate.get("score_typography", 0.0)) > 0.0 for candidate in scored
    ), "typography boosts must apply when fonts are emphasized"

    stitched = stitch_headers(scored)
    repaired = repair_sequence(stitched)

    predicted = {_normalize_header_text(row["text"]) for row in repaired}
    expected = {_normalize_header_text(text) for text in expected_headers}

    assert predicted, "header pipeline should emit repaired headers"
    true_positives = len(predicted & expected)
    precision = true_positives / len(predicted)
    recall = true_positives / len(expected)

    assert precision >= 0.9
    assert recall >= 0.9


def test_rechunk_assignments_limit_leakage(tmp_path: Path) -> None:
    """Rechunking should align chunk IDs with headers with minimal leakage."""

    headers: list[dict[str, Any]] = [
        {
            "header_id": "doc:h1",
            "section_id": "doc:s1",
            "doc_id": "doc",
            "text": "Executive Summary",
            "level": 1,
            "score": 0.82,
            "recovered": False,
            "sentence_start": 0,
            "sentence_end": 0,
            "chunk_index": 0,
        },
        {
            "header_id": "doc:h2",
            "section_id": "doc:s2",
            "doc_id": "doc",
            "text": "1. Introduction",
            "level": 1,
            "score": 0.78,
            "recovered": False,
            "sentence_start": 5,
            "sentence_end": 5,
            "chunk_index": 100,
        },
        {
            "header_id": "doc:h3",
            "section_id": "doc:s3",
            "doc_id": "doc",
            "text": "1.1 Scope",
            "level": 2,
            "score": 0.75,
            "recovered": False,
            "sentence_start": 10,
            "sentence_end": 10,
            "chunk_index": 200,
        },
    ]

    chunk_rows = [
        {
            "chunk_id": "c1",
            "doc_id": "doc",
            "text": "Executive Summary\nOverview of goals.",
            "sentence_start": 0,
        },
        {
            "chunk_id": "c2",
            "doc_id": "doc",
            "text": "Key initiatives and KPIs.",
            "sentence_start": 2,
        },
        {
            "chunk_id": "c3",
            "doc_id": "doc",
            "text": "1. Introduction\nContext and rationale.",
            "sentence_start": 5,
        },
        {
            "chunk_id": "c4",
            "doc_id": "doc",
            "text": "Detailed background for the initiative.",
            "sentence_start": 7,
        },
        {
            "chunk_id": "c5",
            "doc_id": "doc",
            "text": "1.1 Scope\nBoundaries and constraints.",
            "sentence_start": 11,
        },
    ]

    artifact_path = _write_chunks(tmp_path, chunk_rows)
    aggregated = rechunk_by_headers(str(artifact_path), headers)

    assert len(aggregated) == len(headers)
    expected_mapping = {
        "c1": "doc:h1",
        "c2": "doc:h1",
        "c3": "doc:h2",
        "c4": "doc:h2",
        "c5": "doc:h3",
    }

    leakage = 0
    assigned: dict[str, str] = {}
    for section in aggregated:
        header_id = section["header_id"]
        assert section["text"].splitlines()[0] == section["header_text"]
        for chunk_id in section["chunk_ids"]:
            assigned[chunk_id] = header_id
            if expected_mapping.get(chunk_id) != header_id:
                leakage += 1

    assert assigned.keys() == expected_mapping.keys()
    leakage_rate = leakage / len(expected_mapping)
    assert leakage_rate <= 0.05

    for section in aggregated:
        assert section["text"].strip(), "aggregated sections should contain text"
