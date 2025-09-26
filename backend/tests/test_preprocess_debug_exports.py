import json

from backend.routes import preprocess


def test_export_preprocess_debug_writes_full_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("FLUIDRAG_DEBUG_DIR", str(tmp_path / "custom-debug"))

    macro_chunks = [
        {"chunk_id": "chunk-1", "document": "Doc Name", "meta": {"foo": "bar"}},
    ]
    micro_chunks = [
        {"micro_id": "micro-1", "text": "example", "page_start": 1, "page_end": 1},
    ]
    response_payload = {"ok": True, "chunks": 1, "micro_chunks": 1}
    preprocess_debug_payload = {"preprocess": {"chunking": {"summary": {"micro_chunk_count": 1}}}}
    chunk_config = {
        "micro": {"size": 123},
        "macro": {"overlap": 10},
        "token_chunker": {"micro_max_tokens": 512, "micro_overlap_tokens": 24},
    }
    pages = [{"page": 1, "text": "Sample text"}]

    outfile = preprocess.export_preprocess_debug(
        session_id="sess-123",
        doc_id="doc-123",
        doc_name="Doc 123",
        macro_chunks=macro_chunks,
        micro_chunks=micro_chunks,
        response_payload=response_payload,
        preprocess_debug_payload=preprocess_debug_payload,
        chunk_config=chunk_config,
        page_records=pages,
        cache_hit=False,
    )

    assert outfile.exists()
    data = json.loads(outfile.read_text(encoding="utf-8"))

    assert data["doc_id"] == "doc-123"
    assert data["doc_name"] == "Doc 123"
    assert data["session_id"] == "sess-123"
    assert data["cache_hit"] is False
    assert data["macro_chunks"][0]["chunk_id"] == "chunk-1"
    assert data["micro_chunks"][0]["micro_id"] == "micro-1"
    assert data["response"]["chunks"] == 1
    assert data["preprocess_debug"]["preprocess"]["chunking"]["summary"]["micro_chunk_count"] == 1
    assert data["config"]["micro"]["size"] == 123
    assert data["pages"][0]["page"] == 1

