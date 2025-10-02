"""Integration test verifying the guarded upload pipeline."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.adapters.storage import (
    StorageAdapter,
    assert_no_unmanaged_writes,
    get_storage_guard,
    reset_storage_guard,
)
from backend.app.services.parser_service import parse_and_enrich
from backend.app.services.upload_service import ensure_normalized
from backend.app.config import get_settings
from backend.app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture()
def test_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isolate settings and storage guard for the integration test."""

    artifact_root = tmp_path / "artifacts"
    monkeypatch.setenv("FLUIDRAG_OFFLINE", "true")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifact_root))
    get_settings.cache_clear()
    reset_storage_guard()
    yield artifact_root
    reset_storage_guard()
    get_settings.cache_clear()


@pytest.fixture()
def app_client(test_environment: Path) -> TestClient:
    """Return a FastAPI test client bound to the upload routes."""

    app = create_app()
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture()
def storage_adapter_spy(monkeypatch: pytest.MonkeyPatch):
    """Spy on StorageAdapter.save_source_pdf invocations."""

    calls: list[dict[str, object]] = []
    original = StorageAdapter.save_source_pdf

    def traced(self, *, doc_id: str, filename: str | None, payload: bytes):
        path = original(self, doc_id=doc_id, filename=filename, payload=payload)
        calls.append(
            {
                "doc_id": doc_id,
                "filename": filename,
                "bytes": len(payload),
                "path": path,
            }
        )
        return path

    monkeypatch.setattr(StorageAdapter, "save_source_pdf", traced)

    class Spy:
        @property
        def called(self) -> bool:
            return bool(calls)

        def calls_for(self, doc_id: str) -> int:
            return sum(1 for call in calls if call["doc_id"] == doc_id)

        def paths(self) -> list[Path]:
            return [call["path"] for call in calls]

    return Spy()


def _epf_pdf_path() -> Path:
    pdf_path = Path("Epf, Co.pdf")
    if not pdf_path.is_file():
        raise FileNotFoundError(
            "Expected 'Epf, Co.pdf' to exist in the repository root for integration tests."
        )
    return pdf_path


def test_upload_pdf_uses_app_functions_only(
    app_client: TestClient,
    storage_adapter_spy,
    test_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uploading a PDF must flow through controller → service → storage adapter."""

    pdf_path = _epf_pdf_path()
    with pdf_path.open("rb") as handle:
        files = {"file": (pdf_path.name, io.BytesIO(handle.read()), "application/pdf")}
        response = app_client.post("/upload/pdf", files=files)

    assert response.status_code == 200
    payload = response.json()
    doc_id = payload.get("doc_id")
    assert doc_id, "doc_id missing from upload response"

    assert storage_adapter_spy.called, "StorageAdapter.save_source_pdf was not invoked"
    assert storage_adapter_spy.calls_for(doc_id) >= 1

    managed_path = test_environment / doc_id / "source.pdf"
    assert managed_path.is_file(), f"Missing managed source PDF at {managed_path}"
    guard_paths = {path.resolve() for path in get_storage_guard().recorded_paths()}
    assert managed_path.resolve() in guard_paths

    assert_no_unmanaged_writes()

    existing_pdfs = {path.resolve() for path in test_environment.rglob("*.pdf")}
    reset_storage_guard()

    def blocked(self, *, doc_id: str, filename: str | None, payload: bytes):
        raise RuntimeError("storage adapter blocked")

    monkeypatch.setattr(StorageAdapter, "save_source_pdf", blocked)

    with pdf_path.open("rb") as handle:
        files = {"file": (pdf_path.name, io.BytesIO(handle.read()), "application/pdf")}
        failure = app_client.post("/upload/pdf", files=files)

    assert failure.status_code >= 500
    new_pdfs = {path.resolve() for path in test_environment.rglob("*.pdf")}
    assert new_pdfs == existing_pdfs, "Unexpected unmanaged PDF write detected"


def test_repo_pdf_can_be_normalized_and_parsed(test_environment: Path) -> None:
    """The canonical EPF RFQ must normalize and parse end-to-end."""

    pdf_path = _epf_pdf_path()

    normalized = ensure_normalized(file_name=str(pdf_path))
    normalized_path = Path(normalized.normalized_path)
    assert normalized_path.is_file()

    source_path = Path(normalized.source_path)
    assert source_path.is_file()
    guard_paths = {path.resolve() for path in get_storage_guard().recorded_paths()}
    assert source_path.resolve() in guard_paths

    enriched = parse_and_enrich(normalized.doc_id, normalized.normalized_path)
    enriched_path = Path(enriched.enriched_path)
    assert enriched_path.is_file()
    assert enriched.summary.get("block_count", 0) >= 50


def test_parsing_report_is_emitted_with_summary(test_environment: Path) -> None:
    """Persist a structured report showing the parse summary for the EPF PDF."""

    pdf_path = _epf_pdf_path()

    normalized = ensure_normalized(file_name=str(pdf_path))
    parsed = parse_and_enrich(normalized.doc_id, normalized.normalized_path)

    enriched_path = Path(parsed.enriched_path)
    assert enriched_path.is_file(), "Missing enriched artifact"
    enriched_payload = json.loads(enriched_path.read_text(encoding="utf-8"))
    block_total = len(enriched_payload.get("blocks", []))
    assert block_total == parsed.summary.get("block_count")

    report_path = enriched_path.with_name("parse_report.json")
    report_payload = {
        "doc_id": parsed.doc_id,
        "language": parsed.language,
        "summary": parsed.summary,
        "metrics": parsed.metrics,
        "blocks": block_total,
    }
    report_path.write_text(json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    assert report_path.is_file(), "Parse report was not written"
    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved_report["doc_id"] == parsed.doc_id
    assert saved_report["summary"].get("block_count", 0) >= 50
    assert saved_report["language"] == parsed.language
    assert saved_report["blocks"] == block_total
