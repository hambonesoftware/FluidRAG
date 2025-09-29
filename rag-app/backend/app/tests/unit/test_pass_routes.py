"""Unit tests for passes routes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from ...config import get_settings
from ...routes import passes as passes_routes


def _artifact_root() -> Path:
    return get_settings().artifact_root_path


def _write_manifest(root: Path, doc_id: str, data: dict[str, object]) -> Path:
    manifest_dir = root / doc_id / "passes"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "manifest.json"
    manifest_path.write_text(json.dumps(data), encoding="utf-8")
    return manifest_path


def test_list_passes_returns_manifest(tmp_path: Path) -> None:
    _ = tmp_path
    doc_id = "abc123"
    root = _artifact_root()
    pass_file = root / doc_id / "passes" / "summary.json"
    pass_file.parent.mkdir(parents=True, exist_ok=True)
    pass_file.write_text(json.dumps({"content": "ok"}), encoding="utf-8")
    _write_manifest(
        root,
        doc_id,
        {"passes": {"summary": str(pass_file)}},
    )

    payload = asyncio.run(passes_routes.list_passes(doc_id))
    assert payload == {"doc_id": doc_id, "passes": {"summary": str(pass_file)}}


def test_list_passes_missing_manifest(tmp_path: Path) -> None:
    _ = tmp_path
    with pytest.raises(HTTPException) as exc:
        asyncio.run(passes_routes.list_passes("missing"))
    assert exc.value.status_code == 404


def test_list_passes_invalid_manifest_logs_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _ = tmp_path
    doc_id = "doc"
    manifest_path = _write_manifest(_artifact_root(), doc_id, {"passes": {}})
    manifest_path.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")

    with caplog.at_level("ERROR"):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(passes_routes.list_passes(doc_id))

    assert exc.value.status_code == 500
    assert any("passes.manifest_invalid" in record.message for record in caplog.records)


def test_get_pass_returns_payload(tmp_path: Path) -> None:
    _ = tmp_path
    doc_id = "doc"
    root = _artifact_root()
    pass_dir = root / doc_id / "passes"
    pass_dir.mkdir(parents=True, exist_ok=True)
    pass_file = pass_dir / "summary.json"
    pass_file.write_text(json.dumps({"summary": "value"}), encoding="utf-8")
    # Store relative path to exercise resolution logic
    _write_manifest(root, doc_id, {"passes": {"summary": "summary.json"}})

    payload = asyncio.run(passes_routes.get_pass(doc_id, "summary"))
    assert payload["summary"] == "value"


def test_get_pass_missing_name(tmp_path: Path) -> None:
    _ = tmp_path
    _write_manifest(_artifact_root(), "doc", {"passes": {"other": "missing.json"}})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(passes_routes.get_pass("doc", "summary"))
    assert exc.value.status_code == 404


def test_get_pass_invalid_manifest_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_passes(doc_id: str) -> dict[str, object]:
        return {"doc_id": doc_id, "passes": {"summary": 1}}

    monkeypatch.setattr(passes_routes, "list_passes", fake_list_passes)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(passes_routes.get_pass("doc", "summary"))
    assert exc.value.status_code == 500


def test_get_pass_missing_file_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _ = tmp_path
    _write_manifest(_artifact_root(), "doc", {"passes": {"summary": "summary.json"}})

    with caplog.at_level("WARNING"):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(passes_routes.get_pass("doc", "summary"))

    assert exc.value.status_code == 404
    assert any("passes.get_missing" in record.message for record in caplog.records)


def test_get_pass_payload_not_dict(tmp_path: Path) -> None:
    _ = tmp_path
    doc_id = "doc"
    root = _artifact_root()
    pass_file = root / doc_id / "passes" / "raw.json"
    pass_file.parent.mkdir(parents=True, exist_ok=True)
    pass_file.write_text("[]", encoding="utf-8")
    _write_manifest(root, doc_id, {"passes": {"raw": str(pass_file)}})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(passes_routes.get_pass(doc_id, "raw"))
    assert exc.value.status_code == 500
