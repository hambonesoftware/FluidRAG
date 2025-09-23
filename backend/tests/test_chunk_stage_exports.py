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
        "text": "alpha",
        "page": 1,
        "section_number": "1",
        "section_name": "Intro",
    }
    state = SimpleNamespace(
        pre_chunks=[dict(base_chunk)],
        file_path=str(tmp_path / "doc.pdf"),
        filename="Doc.pdf",
        file_hash="hash123",
        tmpdir=str(tmp_path),
    )

    monkeypatch.setattr(chunking, "get_state", lambda sid: state if sid == session_id else None)
    monkeypatch.setattr(chunking, "fluid_refine_chunks", lambda chunks: [dict(chunk, fluid=True) for chunk in chunks])
    monkeypatch.setattr(chunking, "hep_cluster_chunks", lambda chunks: [dict(chunk, hep=True) for chunk in chunks])
    monkeypatch.setattr(chunking, "get_preprocess_cache", lambda file_hash: None)
    monkeypatch.setattr(chunking.os, "makedirs", lambda path, exist_ok=True: None)

    result = chunking.ensure_chunks(session_id)

    assert len(result) == 1
    final_chunk = result[0]
    assert final_chunk["text"] == "alpha"
    assert final_chunk["page"] == 1
    assert final_chunk["section_number"] == "1"
    assert final_chunk["section_name"] == "Intro"
    assert final_chunk["document"] == "Doc.pdf"
    assert final_chunk["page_start"] == 1
    assert final_chunk["page_end"] == 1
    assert final_chunk["meta"] == {}
    assert final_chunk["fluid"] is True
    assert final_chunk["hep"] is True
    snapshots = state.chunk_stage_snapshots
    assert set(snapshots) == {
        "raw_chunking",
        "standard_chunks",
        "fluid_chunks",
        "hep_chunks",
    }
    assert "document" not in snapshots["raw_chunking"][0]
    assert snapshots["standard_chunks"][0]["document"] == "Doc.pdf"
    assert snapshots["fluid_chunks"][0]["fluid"] is True
    assert snapshots["hep_chunks"][0]["hep"] is True


def test_export_pass_stage_snapshots_writes_files(monkeypatch, tmp_path):
    session_id = "sess-export"
    stage_map = {
        "raw_chunking": [{"text": "a"}],
        "standard_chunks": [{"text": "a", "document": "Doc"}],
        "fluid_chunks": [{"text": "a", "fluid": True}],
        "hep_chunks": [{"text": "a", "hep": True}],
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
    assert set(data["stages"]) == {
        "raw_chunking",
        "standard_chunks",
        "fluid_chunks",
        "hep_chunks",
    }
    assert data["stages"]["raw_chunking"]["chunk_count"] == 1
    assert data["stages"]["hep_chunks"]["chunk_count"] == 1
