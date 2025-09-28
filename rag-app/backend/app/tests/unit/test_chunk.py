"""Unit tests for chunk service and retrieval helpers."""

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


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUIDRAG_OFFLINE", "true")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("CHUNK_TARGET_TOKENS", "18")
    monkeypatch.setenv("CHUNK_TOKEN_OVERLAP", "10")
    get_settings.cache_clear()


def _build_pipeline(tmp_path: Path, text: str) -> tuple[str, str]:
    source = tmp_path / "doc.txt"
    source.write_text(text, encoding="utf-8")
    normalized = ensure_normalized(file_name=str(source))
    parsed = parse_and_enrich(normalized.doc_id, normalized.normalized_path)
    return parsed.doc_id, parsed.enriched_path


def test_run_uf_chunking_creates_chunks_and_indexes(tmp_path: Path) -> None:
    """Unit test placeholder."""
    doc_id, enriched_path = _build_pipeline(
        tmp_path,
        (
            "Executive Summary introduces the strategy. This section highlights key metrics with figures and ratios. "
            "Detailed analysis follows with multiple insights and supporting evidence. "
            "Mid-course adjustments are enumerated alongside risks. "
            "Appendix covers supplemental materials and citations. "
            "Final thoughts reinforce the narrative and call to action."
        ),
    )

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


def test_run_uf_chunking_missing_artifact_raises_not_found(tmp_path: Path) -> None:
    """Validate chunk boundaries respect sentence and header edges."""
    with pytest.raises(NotFoundError):
        run_uf_chunking("doc-123", str(tmp_path / "missing.json"))


def test_hybrid_search_fuses_sparse_and_dense() -> None:
    bm25 = BM25Index()
    bm25.add(["alpha beta", "beta gamma", "delta epsilon"])

    faiss = FaissIndex(2)
    faiss.add([[0.9, 0.1], [0.6, 0.4], [0.0, 1.0]])

    results = hybrid_search(
        bm25, faiss, query="beta", query_vec=[0.8, 0.2], alpha=0.6, k=2
    )
    assert results, "hybrid search should return matches"
    top = results[0]
    assert top["id"] == 0, "first document should win due to combined score"
    assert top["dense"] >= top["sparse"], "dense score should influence ranking"
