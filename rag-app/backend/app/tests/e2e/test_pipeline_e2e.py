"""E2E test covering the orchestrator pipeline routes."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ...config import get_settings
from ...main import create_app

pytestmark = pytest.mark.phase6


@pytest.fixture
def client() -> TestClient:
    """Return a FastAPI test client bound to the orchestrator routes."""

    return TestClient(create_app())


def test_pipeline_run_endpoint(
    sample_pdf_path: Path,
    expected_sections: dict[str, list[str]],
    client: TestClient,
) -> None:
    """Run the full pipeline against the curated fixture and assert artifacts."""

    response = client.post("/pipeline/run", json={"file_name": str(sample_pdf_path)})
    assert response.status_code == 200
    payload = response.json()
    doc_id = payload["doc_id"]
    assert doc_id
    assert payload["normalize"]["block_count"] >= 4
    assert set(payload["passes"]["passes"].keys()) == set(expected_sections["passes"])

    settings = get_settings()
    doc_root = Path(settings.artifact_root_path) / doc_id
    assert doc_root.exists()

    status_response = client.get(f"/pipeline/status/{doc_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["doc_id"] == doc_id
    assert status_payload["pipeline_audit"]["pipeline"]["stage"] == "pipeline.run"
    assert status_payload["pipeline_audit"]["stages"], "expected pipeline stages"
    assert set(status_payload["passes"].keys()) == set(expected_sections["passes"])

    results_response = client.get(f"/pipeline/results/{doc_id}")
    assert results_response.status_code == 200
    results_payload = results_response.json()
    assert set(results_payload["passes"].keys()) == set(expected_sections["passes"])
    sample_pass = next(iter(results_payload["passes"].values()))
    assert sample_pass["answer"], "passes should include synthesized answers"

    manifest = results_payload["manifest"]
    first_pass = expected_sections["passes"][0]
    artifact_path = Path(manifest["passes"][first_pass])
    stream_response = client.get(
        "/pipeline/artifacts", params={"path": str(artifact_path)}
    )
    assert stream_response.status_code == 200
    assert stream_response.content == artifact_path.read_bytes()
