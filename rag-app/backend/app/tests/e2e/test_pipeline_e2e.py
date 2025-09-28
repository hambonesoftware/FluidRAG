from __future__ import annotations

import base64
from pathlib import Path

from fastapi.testclient import TestClient

from ...main import create_app


def load_test_pdf_paths() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "sample.pdf"


def test_pipeline_e2e(tmp_path: Path) -> None:
    client = TestClient(create_app())
    pdf_path = load_test_pdf_paths()
    payload = {
        "file_name": "sample.pdf",
        "content": base64.b64encode(pdf_path.read_bytes()).decode("utf-8"),
        "content_type": "application/pdf",
    }
    response = client.post("/orchestrator/run", json=payload)
    assert response.status_code == 200
    doc_id = response.json()["doc_id"]

    status = client.get(f"/orchestrator/{doc_id}/status")
    assert status.json()["status"] == "complete"

    results = client.get(f"/orchestrator/{doc_id}/results")
    assert results.status_code == 200
    assert results.json()["passes"]


def test_pipeline_real_pdf() -> None:
    pdf_path = load_test_pdf_paths()
    assert pdf_path.exists()
