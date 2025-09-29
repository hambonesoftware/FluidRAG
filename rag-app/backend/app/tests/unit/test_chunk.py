from __future__ import annotations

import json
from pathlib import Path

import pytest

from ...adapters.vectors import BM25Index, FaissIndex, hybrid_search
from ...config import get_settings
from ...services.chunk_service import ChunkResult, run_uf_chunking
from ...services.parser_service import parse_and_enrich
from ...services.upload_service import ensure_normalized
from ...util.errors import NotFoundError

pytestmark = pytest.mark.phase4


def _build_pipeline(
    sample_pdf_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, str]:
    monkeypatch.setenv("CHUNK_TARGET_TOKENS", "24")
    monkeypatch.setenv("CHUNK_TOKEN_OVERLAP", "8")
    get_settings.cache_clear()
    normalized = ensure_normalized(file_name=str(sample_pdf_path))
    parsed = parse_and_enrich(normalized.doc_id, normalized.normalized_path)
    return parsed.doc_id, parsed.enriched_path


def test_uf_chunk_pipeline(
    sample_pdf_path: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """UF chunking emits artifacts and builds local index using curated fixture."""

    doc_id, enriched_path = _build_pipeline(sample_pdf_path, monkeypatch)

    result: ChunkResult = run_uf_chunking(doc_id, enriched_path)
    chunks_path = Path(result.chunks_path)
    manifest_path = Path(result.index_manifest_path or "")
    audit_path = chunks_path.with_name("chunk.audit.json")

    assert chunks_path.exists(), "uf_chunks.jsonl should be written"
    assert manifest_path.exists(), "index manifest should exist"
    assert audit_path.exists(), "chunk audit record should exist"

    rows = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(rows) >= 2, "chunking should produce multiple segments for long text"
    assert rows[0]["sentence_start"] == 0
    assert rows[0]["sentence_end"] >= rows[0]["sentence_start"]
    assert (
        rows[1]["sentence_start"] <= rows[0]["sentence_end"]
    ), "overlap should reuse context"
    assert rows[0]["token_count"] <= 40
    assert any("Controls" in row["text"] for row in rows)

    with pytest.raises(NotFoundError):
        run_uf_chunking("doc-123", str(tmp_path / "missing.json"))

    bm25 = BM25Index()
    bm25.add(["alpha beta", "beta gamma", "delta epsilon"])

    dense_vectors = FaissIndex(2)
    dense_vectors.add([[0.9, 0.1], [0.6, 0.4], [0.0, 1.0]])

    results = hybrid_search(
        bm25,
        dense_vectors,
        query="beta",
        query_vec=[0.8, 0.2],
        alpha=0.6,
        k=2,
    )
    assert results, "hybrid search should return matches"
    top = results[0]
    assert top["dense"] >= top["sparse"], "dense score should influence ranking"


def test_uf_chunk_boundaries(
    sample_pdf_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validate chunk boundaries respect sentence and header edges."""
    doc_id, enriched_path = _build_pipeline(sample_pdf_path, monkeypatch)

    result: ChunkResult = run_uf_chunking(doc_id, enriched_path)
    chunks_path = Path(result.chunks_path)
    rows = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line
    ]

    assert rows, "chunking should yield at least one chunk"
    first = rows[0]
    assert first["sentence_start"] == 0
    for current, nxt in zip(rows, rows[1:], strict=False):
        assert current["sentence_start"] <= current["sentence_end"]
        assert nxt["sentence_start"] <= nxt["sentence_end"]
        assert (
            nxt["sentence_start"] <= current["sentence_end"]
        ), "subsequent chunk should overlap or abut previous sentences"
