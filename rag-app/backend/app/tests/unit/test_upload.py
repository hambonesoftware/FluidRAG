"""Tests for upload normalization pipeline."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from ...config import get_settings
from ...services.upload_service import NormalizedDoc, ensure_normalized
from ...services.upload_service.packages.guards.validators import validate_upload_inputs
from ...util.errors import ValidationError


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLUIDRAG_OFFLINE", "true")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    get_settings.cache_clear()


def _write_sample(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str) -> Path:
    path = tmp_path / "sample.txt"
    path.write_text(text, encoding="utf-8")
    return path


def test_validate_upload_inputs_rejects_invalid() -> None:
    with pytest.raises(ValidationError):
        validate_upload_inputs()
    with pytest.raises(ValidationError):
        validate_upload_inputs(file_id="   ")
    with pytest.raises(ValidationError):
        validate_upload_inputs(file_name="../danger.txt")
    with pytest.raises(ValidationError):
        validate_upload_inputs(file_name="https://example.com/file.pdf")


def test_ensure_normalized_emits_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sample_text = (
        "INTRODUCTION\n\n"
        "- bullet one\n"
        "- bullet two\n\n"
        "Table\nA|B\n1|2\n\n"
        "[image:diagram]\n\n"
        "See https://example.com"
    )
    source = _write_sample(monkeypatch, tmp_path, sample_text)

    result: NormalizedDoc = ensure_normalized(file_name=str(source))
    normalized_path = Path(result.normalized_path)
    manifest_path = Path(result.manifest_path)

    assert normalized_path.exists(), "normalize.json should exist"
    assert manifest_path.exists(), "manifest should exist"

    normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
    assert normalized_payload["stats"]["block_count"] >= 2
    assert normalized_payload["stats"]["avg_coverage"] > 0

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checksum = sha256(normalized_path.read_bytes()).hexdigest()
    assert manifest["checksum"] == checksum
    assert manifest["doc_id"] == result.doc_id


def test_ensure_normalized_idempotent_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sample_text = """


    [image:logo]
    """
    source = _write_sample(monkeypatch, tmp_path, sample_text)
    first = ensure_normalized(file_name=str(source))
    second = ensure_normalized(file_name=str(source))

    assert Path(first.normalized_path).read_text(encoding="utf-8")
    assert Path(second.normalized_path).read_text(encoding="utf-8")
    assert first.doc_id != second.doc_id, "doc ids should be unique across runs"
