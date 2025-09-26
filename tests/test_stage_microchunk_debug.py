import json

from stages import build_stage_payload


def test_microchunk_debug_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    stage_chunks = [
        {
            "text": "Section 1 text with enough words to create microchunks.",
            "section_id": "1.0",
            "section_title": "Intro",
        },
        {
            "text": "Continuation of section text to ensure overlap handling.",
            "section_id": "1.0",
            "section_title": "Intro",
        },
    ]

    result = build_stage_payload("doc-123", stage_chunks, token_size=20, overlap=5)

    debug_dir = tmp_path / "debug" / "chunks"
    assert debug_dir.is_dir()

    debug_file = debug_dir / "doc-123.jsonl"
    assert debug_file.is_file()

    lines = debug_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(result.microchunks)

    first_chunk = json.loads(lines[0])
    assert first_chunk["doc_id"] == "doc-123"
    assert "text" in first_chunk
