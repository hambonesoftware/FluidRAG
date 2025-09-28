from __future__ import annotations

from pathlib import Path

from ...services.chunk_service import run_uf_chunking
from ...services.header_service import join_and_rechunk
from ...services.upload_service import ensure_normalized


def test_test_headers() -> None:
    sample_path = Path(__file__).resolve().parents[2] / "data" / "sample.pdf"
    normalized = ensure_normalized(
        file_name="sample.pdf",
        content=sample_path.read_bytes(),
        content_type="application/pdf",
    )
    run_uf_chunking(doc_id=normalized.doc_id, normalize_artifact=normalized.manifest_path)
    chunks_artifact = str(Path(normalized.manifest_path).parent / "chunks.jsonl")
    header_result = join_and_rechunk(doc_id=normalized.doc_id, chunks_artifact=chunks_artifact)
    assert header_result.headers
    assert header_result.sections


def test_sequence_repair_recovers_missing_headers() -> None:
    sample_path = Path(__file__).resolve().parents[2] / "data" / "sample.pdf"
    normalized = ensure_normalized(
        file_name="sample.pdf",
        content=sample_path.read_bytes(),
        content_type="application/pdf",
    )
    run_uf_chunking(doc_id=normalized.doc_id, normalize_artifact=normalized.manifest_path)
    chunks_artifact = str(Path(normalized.manifest_path).parent / "chunks.jsonl")
    header_result = join_and_rechunk(doc_id=normalized.doc_id, chunks_artifact=chunks_artifact)
    levels = [header.level for header in header_result.headers]
    assert all(level >= 1 for level in levels)
