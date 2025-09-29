"""Shared fixtures for backend test suite."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO

import pytest

from backend.app.config import get_settings
from backend.app.util.logging import get_logger

FIXTURE_ROOT = Path(__file__).resolve().parent / "data"


@pytest.fixture(scope="session")
def fixture_root() -> Path:
    """Return the root directory containing curated test fixtures."""

    return FIXTURE_ROOT


@pytest.fixture(scope="session")
def sample_pdf_path(
    fixture_root: Path, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Materialize the canonical engineering overview document as a pseudo-PDF."""

    source = fixture_root / "documents" / "engineering_overview.txt"
    if not source.exists():  # pragma: no cover - defensive guard
        raise FileNotFoundError(source)

    staging_dir = tmp_path_factory.mktemp("engineering_overview")
    pdf_path = staging_dir / "engineering_overview.pdf"
    pdf_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return pdf_path


@pytest.fixture(scope="session")
def expected_sections(fixture_root: Path) -> dict[str, list[str]]:
    """Load expected headers and passes for the curated fixture."""

    payload_path = fixture_root / "json" / "expected_sections.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    headers = [str(value) for value in payload.get("expected_headers", [])]
    passes = [str(value) for value in payload.get("expected_passes", [])]
    return {"headers": headers, "passes": passes}


@pytest.fixture(autouse=True)
def _apply_offline_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[None]:
    """Force offline mode and isolated artifact roots for every test."""

    artifact_root = tmp_path / "artifacts"
    monkeypatch.setenv("FLUIDRAG_OFFLINE", "true")
    monkeypatch.setenv("ARTIFACT_ROOT", str(artifact_root))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_logging_streams() -> Iterator[None]:
    """Redirect fluidrag logging handlers to in-memory buffers during tests."""

    root_logger = get_logger()
    buffers: list[tuple[logging.StreamHandler, TextIO]] = []
    for handler in list(root_logger.handlers):
        if not isinstance(handler, logging.StreamHandler):
            continue
        stream = handler.stream
        if stream is None:
            continue
        buffer = io.StringIO()
        buffers.append((handler, stream))
        try:
            handler.setStream(buffer)
        except ValueError:  # pragma: no cover - stream already closed by fixture
            continue
    try:
        yield
    finally:
        for handler, original in buffers:
            handler.setStream(original)
