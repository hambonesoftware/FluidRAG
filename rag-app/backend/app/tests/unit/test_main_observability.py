"""Tests for FastAPI observability middleware."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app


def test_correlation_id_header() -> None:
    app = create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    correlation_id = response.headers.get("x-correlation-id")
    assert correlation_id
    assert response.headers.get("x-response-time-ms")
