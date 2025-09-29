"""Unit tests for orchestrator pipeline routes (phase 7)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ...config import get_settings
from ...contracts.passes import Citation, PassManifest, PassResult
from ...main import create_app
from ...routes import orchestrator as orchestrator_routes
from ...services.chunk_service import ChunkResult
from ...services.header_service import HeaderJoinResult
from ...services.parser_service import ParseResult
from ...services.rag_pass_service import PassJobs
from ...services.upload_service import NormalizedDoc
from ...util.errors import AppError, NotFoundError, ValidationError

pytestmark = pytest.mark.phase7


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Ensure tests run with a clean offline settings cache."""

    monkeypatch.setenv("FLUIDRAG_OFFLINE", "true")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    """Return a FastAPI test client bound to the orchestrator routes."""

    return TestClient(create_app())


def _prepare_normalized_doc(doc_id: str) -> NormalizedDoc:
    artifact_root = get_settings().artifact_root_path
    doc_root = artifact_root / doc_id
    doc_root.mkdir(parents=True, exist_ok=True)

    normalized_path = doc_root / "normalize.json"
    normalized_path.write_text("{}", encoding="utf-8")

    manifest_payload = {
        "doc_id": doc_id,
        "artifact_path": str(normalized_path),
        "kind": "normalize",
        "checksum": "abc123",
        "size": 2,
        "generated_at": "2024-01-01T00:00:00Z",
        "manifest_path": str(doc_root / "normalize.manifest.json"),
    }
    manifest_path = Path(str(manifest_payload["manifest_path"]))
    manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")

    return NormalizedDoc(
        doc_id=doc_id,
        normalized_path=str(normalized_path),
        manifest_path=str(manifest_path),
        avg_coverage=0.6,
        block_count=4,
        ocr_performed=False,
    )


def test_pipeline_run_creates_manifest_and_results(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    doc_id = "doc-123"
    normalized_doc = _prepare_normalized_doc(doc_id)
    doc_root = get_settings().artifact_root_path / doc_id
    passes_dir = doc_root / "passes"
    passes_dir.mkdir(parents=True, exist_ok=True)

    chunk_path = doc_root / "header_chunks.jsonl"
    chunk_path.write_text(json.dumps({"chunk_id": "c1"}) + "\n", encoding="utf-8")

    parse_result = ParseResult(
        doc_id=doc_id,
        enriched_path=str(doc_root / "parse.enriched.json"),
        language="en",
        summary={"sections": 2},
        metrics={"duration_ms": 12.5},
    )
    chunk_result = ChunkResult(
        doc_id=doc_id,
        chunks_path=str(chunk_path),
        chunk_count=1,
        index_manifest_path=None,
    )
    headers_result = HeaderJoinResult(
        doc_id=doc_id,
        headers_path=str(doc_root / "headers.json"),
        section_map_path=str(doc_root / "section_map.json"),
        header_chunks_path=str(chunk_path),
        header_count=1,
        recovered_count=0,
    )

    pass_result = PassResult(
        doc_id=doc_id,
        pass_id="mechanical",
        pass_name="Mechanical",
        answer="Torque requirement is 50 Nm.",
        citations=[Citation(chunk_id="doc:c1", header_path="Mechanics")],
        retrieval=[],
        context="Torque requirement is 50 Nm.",
        prompt={"system": "sys", "user": "usr"},
    )
    pass_result_path = passes_dir / "mechanical.json"
    pass_result_path.write_text(json.dumps(pass_result.model_dump()), encoding="utf-8")

    def _fake_run_passes(doc_id_arg: str, header_chunks_path: str) -> PassJobs:
        assert doc_id_arg == doc_id
        assert header_chunks_path == str(chunk_path)
        manifest = PassManifest(
            doc_id=doc_id,
            passes={"mechanical": str(pass_result_path)},
        )
        manifest_path = passes_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest.model_dump()), encoding="utf-8")
        return PassJobs(
            doc_id=doc_id,
            manifest_path=str(manifest_path),
            passes=manifest.passes,
        )

    monkeypatch.setattr(
        orchestrator_routes, "ensure_normalized", lambda *args, **kwargs: normalized_doc
    )
    monkeypatch.setattr(
        orchestrator_routes, "parse_and_enrich", lambda *args, **kwargs: parse_result
    )
    monkeypatch.setattr(
        orchestrator_routes, "run_uf_chunking", lambda *args, **kwargs: chunk_result
    )
    monkeypatch.setattr(
        orchestrator_routes, "join_and_rechunk", lambda *args, **kwargs: headers_result
    )
    monkeypatch.setattr(orchestrator_routes, "run_passes", _fake_run_passes)

    response = client.post("/pipeline/run", json={"file_name": "doc.pdf"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["doc_id"] == doc_id
    assert payload["passes"]["passes"]["mechanical"].endswith("mechanical.json")
    assert Path(payload["audit_path"]).exists(), "pipeline audit should be written"

    status_response = client.get(f"/pipeline/status/{doc_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["passes"] == {"mechanical": str(pass_result_path)}
    assert status_payload["pipeline_audit"]["stage"] == "pipeline.run"

    results_response = client.get(f"/pipeline/results/{doc_id}")
    assert results_response.status_code == 200
    results_payload = results_response.json()
    assert "manifest" in results_payload
    assert results_payload["passes"]["mechanical"]["answer"].startswith("Torque")

    stream_response = client.get(
        "/pipeline/artifacts", params={"path": str(pass_result_path)}
    )
    assert stream_response.status_code == 200
    assert stream_response.content == pass_result_path.read_bytes()


def test_run_pipeline_handles_validation_and_not_found(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    def _raise_validation(*_args: object, **_kwargs: object) -> None:
        raise ValidationError("missing inputs")

    monkeypatch.setattr(orchestrator_routes, "ensure_normalized", _raise_validation)
    resp = client.post("/pipeline/run", json={"file_name": "doc.pdf"})
    assert resp.status_code == 400

    normalized_doc = _prepare_normalized_doc("doc-nf")

    def _raise_not_found(*_args: object, **_kwargs: object) -> None:
        raise NotFoundError("missing artifact")

    monkeypatch.setattr(
        orchestrator_routes, "ensure_normalized", lambda *args, **kwargs: normalized_doc
    )
    monkeypatch.setattr(orchestrator_routes, "parse_and_enrich", _raise_not_found)
    resp_nf = client.post("/pipeline/run", json={"file_name": "doc.pdf"})
    assert resp_nf.status_code == 404


def test_run_pipeline_handles_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    normalized_doc = _prepare_normalized_doc("doc-app-error")

    def _raise_app_error(*_args: object, **_kwargs: object) -> None:
        raise AppError("boom")

    monkeypatch.setattr(
        orchestrator_routes, "ensure_normalized", lambda *args, **kwargs: normalized_doc
    )
    monkeypatch.setattr(orchestrator_routes, "parse_and_enrich", _raise_app_error)
    response = client.post("/pipeline/run", json={"file_name": "doc.pdf"})
    assert response.status_code == 500


def test_results_missing_manifest_returns_404(client: TestClient) -> None:
    doc_id = "unknown"
    artifact_root = get_settings().artifact_root_path
    doc_root = artifact_root / doc_id
    doc_root.mkdir(parents=True, exist_ok=True)
    with pytest.raises(FileNotFoundError):
        (doc_root / "passes" / "manifest.json").read_text()

    resp = client.get(f"/pipeline/results/{doc_id}")
    assert resp.status_code == 404


def test_stream_artifact_guards_against_escape(
    client: TestClient, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("danger", encoding="utf-8")

    resp = client.get("/pipeline/artifacts", params={"path": str(outside)})
    assert resp.status_code == 403

    missing = get_settings().artifact_root_path / "doc" / "missing.json"
    resp_missing = client.get("/pipeline/artifacts", params={"path": str(missing)})
    assert resp_missing.status_code == 404
