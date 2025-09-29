"""E2E test covering the orchestrator pipeline routes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ...config import get_settings
from ...main import create_app
from ...services.chunk_service import ChunkResult
from ...services.header_service import HeaderJoinResult
from ...services.parser_service import ParseResult
from ...services.upload_service import NormalizedDoc

pytestmark = pytest.mark.phase6


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUIDRAG_OFFLINE", "true")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_pipeline_run_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    artifact_root = Path(get_settings().artifact_root_path)
    doc_root = artifact_root / "doc"
    doc_root.mkdir(parents=True, exist_ok=True)

    normalized_path = doc_root / "normalize.json"
    normalized_path.write_text(json.dumps({"doc_id": "doc"}), encoding="utf-8")
    manifest_path = doc_root / "manifest.json"
    manifest_payload = {"doc_id": "doc", "checksum": "abc"}
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    enriched_path = doc_root / "parse.enriched.json"
    enriched_path.write_text("{}", encoding="utf-8")

    chunks_path = doc_root / "header_chunks.jsonl"
    chunks = [
        {
            "chunk_id": "doc:c1",
            "text": "Torque requirement is 50 Nm with 200 RPM limit.",
            "token_count": 9,
            "sentence_start": 0,
            "sentence_end": 0,
            "header_path": "Mechanics/Drive",
        },
        {
            "chunk_id": "doc:c2",
            "text": "Controller monitors pressure and temperature sensors.",
            "token_count": 8,
            "sentence_start": 1,
            "sentence_end": 1,
            "header_path": "Controls/Safety",
        },
    ]
    chunks_path.write_text(
        "\n".join(json.dumps(row) for row in chunks) + "\n", encoding="utf-8"
    )

    normalized_doc = NormalizedDoc(
        doc_id="doc",
        normalized_path=str(normalized_path),
        manifest_path=str(manifest_path),
        avg_coverage=0.5,
        block_count=3,
        ocr_performed=False,
    )
    parse_result = ParseResult(
        doc_id="doc",
        enriched_path=str(enriched_path),
        language="en",
        summary={},
        metrics={},
    )
    chunk_result = ChunkResult(
        doc_id="doc",
        chunks_path=str(chunks_path),
        chunk_count=len(chunks),
        index_manifest_path=None,
    )
    headers_result = HeaderJoinResult(
        doc_id="doc",
        headers_path=str(doc_root / "headers.json"),
        section_map_path=str(doc_root / "section_map.json"),
        header_chunks_path=str(chunks_path),
        header_count=2,
        recovered_count=0,
    )

    from ...routes import orchestrator as orchestrator_routes

    monkeypatch.setattr(
        orchestrator_routes, "ensure_normalized", lambda *args, **kwargs: normalized_doc
    )
    monkeypatch.setattr(
        orchestrator_routes,
        "parse_and_enrich",
        lambda *args, **kwargs: parse_result,
    )
    monkeypatch.setattr(
        orchestrator_routes,
        "run_uf_chunking",
        lambda *args, **kwargs: chunk_result,
    )
    monkeypatch.setattr(
        orchestrator_routes,
        "join_and_rechunk",
        lambda *args, **kwargs: headers_result,
    )

    app = create_app()
    client = TestClient(app)

    response = client.post("/pipeline/run", json={"file_name": "sample.txt"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["doc_id"] == "doc"
    assert payload["passes"]["passes"], "passes manifest should not be empty"

    results = client.get("/pipeline/results/doc")
    assert results.status_code == 200
    body = results.json()
    assert "mechanical" in body["passes"]
