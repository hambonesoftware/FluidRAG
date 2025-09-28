from __future__ import annotations

from pathlib import Path

from ...services.chunk_service import run_uf_chunking
from ...services.header_service import join_and_rechunk
from ...services.rag_pass_service import run_all
from ...services.upload_service import ensure_normalized


def test_test_passes() -> None:
    sample_path = Path(__file__).resolve().parents[2] / "data" / "sample.pdf"
    normalized = ensure_normalized(
        file_name="sample.pdf",
        content=sample_path.read_bytes(),
        content_type="application/pdf",
    )
    run_uf_chunking(doc_id=normalized.doc_id, normalize_artifact=normalized.manifest_path)
    chunks_artifact = str(Path(normalized.manifest_path).parent / "chunks.jsonl")
    join_and_rechunk(doc_id=normalized.doc_id, chunks_artifact=chunks_artifact)
    rechunk_artifact = str(Path(chunks_artifact).parent / "headers.json")
    passes_result = run_all(doc_id=normalized.doc_id, rechunk_artifact=rechunk_artifact)
    assert passes_result.passes


def test_hybrid_retrieval_ranking() -> None:
    sample_path = Path(__file__).resolve().parents[2] / "data" / "sample.pdf"
    normalized = ensure_normalized(
        file_name="sample.pdf",
        content=sample_path.read_bytes(),
        content_type="application/pdf",
    )
    run_uf_chunking(doc_id=normalized.doc_id, normalize_artifact=normalized.manifest_path)
    chunks_artifact = str(Path(normalized.manifest_path).parent / "chunks.jsonl")
    join_and_rechunk(doc_id=normalized.doc_id, chunks_artifact=chunks_artifact)
    rechunk_artifact = str(Path(chunks_artifact).parent / "headers.json")
    passes_result = run_all(doc_id=normalized.doc_id, rechunk_artifact=rechunk_artifact)
    for rag_pass in passes_result.passes:
        assert rag_pass.hits
        assert rag_pass.answer["text"]
