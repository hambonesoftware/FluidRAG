from __future__ import annotations

from pathlib import Path

from ...services.chunk_service import run_uf_chunking
from ...services.upload_service import ensure_normalized


def test_test_chunk() -> None:
    sample_path = Path(__file__).resolve().parents[2] / "data" / "sample.pdf"
    normalized = ensure_normalized(
        file_name="sample.pdf",
        content=sample_path.read_bytes(),
        content_type="application/pdf",
    )
    result = run_uf_chunking(doc_id=normalized.doc_id, normalize_artifact=normalized.manifest_path)
    assert result.chunks
    assert all(chunk.doc_id == normalized.doc_id for chunk in result.chunks)


def test_uf_chunk_boundaries() -> None:
    sample_path = Path(__file__).resolve().parents[2] / "data" / "sample.pdf"
    normalized = ensure_normalized(
        file_name="sample.pdf",
        content=sample_path.read_bytes(),
        content_type="application/pdf",
    )
    result = run_uf_chunking(doc_id=normalized.doc_id, normalize_artifact=normalized.manifest_path)
    boundaries = [(chunk.start, chunk.end) for chunk in result.chunks]
    assert boundaries == sorted(boundaries)
