"""Tests for upload normalization pipeline."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from ...services.upload_service import NormalizedDoc, ensure_normalized
from ...services.upload_service.packages.guards.validators import validate_upload_inputs
from ...util.errors import ValidationError


def test_validate_upload_inputs_rejects_invalid() -> None:
    with pytest.raises(ValidationError):
        validate_upload_inputs()
    with pytest.raises(ValidationError):
        validate_upload_inputs(file_id="   ")
    with pytest.raises(ValidationError):
        validate_upload_inputs(file_id="abc def")
    with pytest.raises(ValidationError):
        validate_upload_inputs(file_name="../danger.txt")
    with pytest.raises(ValidationError):
        validate_upload_inputs(file_name="https://example.com/file.pdf")
    with pytest.raises(ValidationError):
        validate_upload_inputs(file_name="unsafe\nname.pdf")


def test_ensure_normalized_emits_manifest(sample_pdf_path: Path) -> None:
    result: NormalizedDoc = ensure_normalized(file_name=str(sample_pdf_path))
    normalized_path = Path(result.normalized_path)
    manifest_path = Path(result.manifest_path)

    assert normalized_path.exists(), "normalize.json should exist"
    assert manifest_path.exists(), "manifest should exist"

    normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
    assert normalized_payload["stats"]["block_count"] >= 4
    assert normalized_payload["stats"]["avg_coverage"] > 0.4
    assert normalized_payload["stats"]["images"] == 1
    assert any("Controls" in page["text"] for page in normalized_payload["pages"])

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checksum = sha256(normalized_path.read_bytes()).hexdigest()
    assert manifest["checksum"] == checksum
    assert manifest["doc_id"] == result.doc_id


def test_ensure_normalized_idempotent_files(sample_pdf_path: Path) -> None:
    first = ensure_normalized(file_name=str(sample_pdf_path))
    second = ensure_normalized(file_name=str(sample_pdf_path))

    assert Path(first.normalized_path).read_text(encoding="utf-8")
    assert Path(second.normalized_path).read_text(encoding="utf-8")
    assert first.doc_id != second.doc_id, "doc ids should be unique across runs"


def test_normalized_manifest_contains_expected_headers(
    sample_pdf_path: Path, expected_sections: dict[str, list[str]]
) -> None:
    result = ensure_normalized(file_name=str(sample_pdf_path))
    normalized_payload = json.loads(
        Path(result.normalized_path).read_text(encoding="utf-8")
    )
    header_candidates = [
        block["text"]
        for page in normalized_payload["pages"]
        for block in page.get("blocks", [])
    ]
    for header in expected_sections["headers"]:
        assert any(text.startswith(header) for text in header_candidates), header
