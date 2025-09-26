import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.pipeline.passes import chunking


@pytest.fixture(autouse=True)
def reset_logging(monkeypatch):
    # Silence log noise during tests
    monkeypatch.setattr(chunking.log, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(chunking.log, "warning", lambda *args, **kwargs: None)


def test_ensure_chunks_records_stage_snapshots(monkeypatch, tmp_path):
    session_id = "sess-stage"
    base_chunk = {
        "micro_id": "uf-001",
        "text": "The system shall maintain 120 psi pressure at all times.",
        "norm_text": "The system shall maintain 120 psi pressure at all times.",
        "page": 1,
        "pages": [1],
        "section_id": "1",
        "section_title": "Intro",
        "sequence_index": 0,
        "lex": {
            "modal_flags": ["shall"],
            "numbers": ["120"],
            "units": ["psi"],
        },
    }
    state = SimpleNamespace(
        uf_chunks=[dict(base_chunk)],
        file_path=str(tmp_path / "doc.pdf"),
        filename="Doc.pdf",
        file_hash="hash123",
        tmpdir=str(tmp_path),
    )

    monkeypatch.setattr(chunking, "get_state", lambda sid: state if sid == session_id else None)
    monkeypatch.setattr(chunking, "get_preprocess_cache", lambda file_hash: None)
    monkeypatch.setattr(chunking.os, "makedirs", lambda path, exist_ok=True: None)

    result = chunking.ensure_chunks(session_id)

    assert len(result) == 1
    final_chunk = result[0]
    assert final_chunk["document"] == "Doc.pdf"
    assert final_chunk["section_number"] == "1"
    assert final_chunk["section_name"] == "Intro"
    assert final_chunk["page_start"] == 1
    assert final_chunk["page_end"] == 1
    meta = final_chunk.get("meta") or {}
    assert meta.get("uf_pipeline") is True
    assert "uf_scores" in meta
    snapshots = state.chunk_stage_snapshots
    keys = set(snapshots)
    assert {"uf_chunks", "uf_scored", "efhg_spans"}.issubset(keys)
    assert snapshots["uf_chunks"][0]["document"] == "Doc.pdf"
    assert snapshots["uf_scored"][0]["meta"]["uf_scores"]
    assert isinstance(snapshots["efhg_spans"], list)
    assert snapshots["raw_chunking"] == snapshots["uf_chunks"]
    assert snapshots["standard_chunks"] == snapshots["uf_scored"]
    assert state.standard_section_lookup


def test_export_pass_stage_snapshots_writes_files(monkeypatch, tmp_path):
    session_id = "sess-export"
    uf_chunks = [{"text": "a", "document": "Doc"}]
    uf_scored = [{"text": "a", "meta": {"uf_scores": {"S_start": 1.0}}}]
    spans = [{"score": 2.1, "start_index": 0, "end_index": 0, "micro_ids": ["uf-1"]}]
    stage_map = {
        "uf_chunks": uf_chunks,
        "uf_scored": uf_scored,
        "efhg_spans": spans,
        "raw_chunking": uf_chunks,
        "standard_chunks": uf_scored,
        "fluid_chunks": uf_scored,
        "hep_chunks": uf_scored,
    }
    state = SimpleNamespace(chunk_stage_snapshots=stage_map)

    monkeypatch.setattr(chunking, "get_state", lambda sid: state if sid == session_id else None)

    chunking.export_pass_stage_snapshots(
        session_id,
        ["Mechanical"],
        include_header=True,
        output_dir=str(tmp_path),
    )

    files = sorted(tmp_path.iterdir())
    assert len(files) == 2
    names = {f.stem.split("_")[0] for f in files}
    assert names == {"Mechanical", "Header"}

    data = json.loads(files[0].read_text())
    assert data["pass"] in {"Mechanical", "Header"}
    assert {"uf_chunks", "uf_scored", "efhg_spans"}.issubset(set(data["stages"]))
    assert data["stages"]["uf_chunks"]["chunk_count"] == 1
    assert data["stages"]["uf_scored"]["chunk_count"] == 1
