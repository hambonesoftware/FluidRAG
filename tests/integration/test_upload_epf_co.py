"""Integration test verifying the guarded upload pipeline."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.adapters.storage import (
    StorageAdapter,
    assert_no_unmanaged_writes,
    get_storage_guard,
    reset_storage_guard,
)
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


def _ensure_sample_pdf() -> Path:
    sample_dir = Path("sample_docs")
    sample_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = sample_dir / "Epf, Co.pdf"
    if not pdf_path.exists():
        pdf_bytes = (
            b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
            b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]/Contents 4 0 R>>endobj\n"
            b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 72 120 Td (hello) Tj ET\nendstream endobj\n"
            b"xref\n0 5\n0000000000 65535 f \n0000000010 00000 n \n"
            b"0000000060 00000 n \n0000000117 00000 n \n0000000210 00000 n \n"
            b"trailer<</Root 1 0 R>>\n%%EOF"
        )
        pdf_path.write_bytes(pdf_bytes)
    return pdf_path


def test_upload_pdf_uses_app_functions_only(
    app_client: TestClient,
    storage_adapter_spy,
    test_environment: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uploading a PDF must flow through controller → service → storage adapter."""

    pdf_path = _ensure_sample_pdf()
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
