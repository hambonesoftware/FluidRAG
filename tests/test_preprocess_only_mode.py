from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from backend.headers import config as cfg_module
from backend.headers.pipeline import run_headers_stage


class _ArtifactSink:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, payload: dict) -> Path:
        path = self.base_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.base_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class _DocFixture:
    def __init__(self, base_dir: Path) -> None:
        headers = [
            {"page": 6, "line_idx": 19, "text": "A1. Robot & EOAT"},
            # String ``line_idx`` ensures normalization coerces to integers.
            {"page": 6, "line_idx": "20", "text": "A2. Vision/Sensing"},
            {"page": 7, "line_idx": 1, "text": "A3. Conveyors & Pallet Handling"},
            {"page": 7, "line_idx": 2, "text": "A4. Controls & Electrical"},
            {"page": 7, "line_idx": 3, "text": "A5. Utilities & Consumption"},
            {"page": 7, "line_idx": 4, "text": "A6. Performance"},
            {"page": 7, "line_idx": 5, "text": "A7. Layout"},
            {"page": 7, "line_idx": 6, "text": "A8. Options (pricing separate)"},
            # Duplicate entry that should be de-duplicated by the finalizer.
            {"page": 7, "line_idx": 4, "text": "A6. Performance"},
        ]
        self.doc_id = "doc-fixture"
        self.preprocess = SimpleNamespace(headers_by_page=headers)
        self.artifacts = _ArtifactSink(base_dir)


@pytest.fixture
def doc_loaded_from_fixtures(tmp_path: Path) -> _DocFixture:
    return _DocFixture(tmp_path / "artifacts")


@pytest.fixture
def cfg() -> cfg_module:
    original_mode = cfg_module.HEADER_MODE
    original_profile = getattr(cfg_module, "HEADER_LEGACY_PROFILE", None)
    try:
        yield cfg_module
    finally:
        cfg_module.HEADER_MODE = original_mode
        if original_profile is not None:
            cfg_module.HEADER_LEGACY_PROFILE = original_profile


def test_appendix_a_from_preprocess_only(doc_loaded_from_fixtures: _DocFixture, cfg: cfg_module) -> None:
    cfg.HEADER_MODE = "preprocess_only"
    headers = run_headers_stage(doc_loaded_from_fixtures)
    got = {(header["page"], header["text"]) for header in headers}
    want = {
        (6, "A1. Robot & EOAT"),
        (6, "A2. Vision/Sensing"),
        (7, "A3. Conveyors & Pallet Handling"),
        (7, "A4. Controls & Electrical"),
        (7, "A5. Utilities & Consumption"),
        (7, "A6. Performance"),
        (7, "A7. Layout"),
        (7, "A8. Options (pricing separate)"),
    }
    assert want.issubset(got), f"Missing headers: {want - got}"

    unique_keys = {
        (header["page"], header.get("line_idx"), header["text"]) for header in headers
    }
    assert len(headers) == len(unique_keys), "Duplicate headers should be removed"

    final_path = doc_loaded_from_fixtures.artifacts.base_dir / "headers_final.json"
    assert final_path.exists(), "final headers artifact not written"
    payload = json.loads(final_path.read_text(encoding="utf-8"))
    assert payload.get("headers_final"), "headers_final.json should contain data"

    # Order should be stable by (page, line_idx) with numeric comparison.
    sorted_headers = sorted(
        headers,
        key=lambda item: (
            item["page"],
            item.get("line_idx") if item.get("line_idx") is not None else 1_000_000,
        ),
    )
    assert headers == sorted_headers, "Headers must retain preprocess ordering"

    tsv_path = doc_loaded_from_fixtures.artifacts.base_dir / "headers_final.tsv"
    assert tsv_path.exists(), "headers_final.tsv should be written for inspection"

