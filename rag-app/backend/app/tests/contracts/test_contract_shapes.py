"""Contract validation for pass service models."""

from __future__ import annotations

from datetime import datetime

import pytest

from ...contracts import (
    Citation,
    NormalizedManifest,
    PassManifest,
    PassResult,
    RetrievalTrace,
)

pytestmark = pytest.mark.phase6


def test_pass_result_schema_roundtrip() -> None:
    """PassResult serialises/deserialises cleanly."""

    trace = RetrievalTrace(
        chunk_id="doc:c1",
        header_path="Intro/Scope",
        score=0.9,
        dense_score=0.5,
        sparse_score=0.7,
        flow_score=0.2,
        energy_score=0.1,
        graph_score=0.3,
        text_preview="Sample text",
    )
    result = PassResult(
        doc_id="doc",
        pass_id="doc:mechanical",
        pass_name="mechanical",
        answer="Answer",
        citations=[
            Citation(
                chunk_id="doc:c1",
                header_path="Intro/Scope",
                sentence_start=0,
                sentence_end=3,
            )
        ],
        retrieval=[trace],
        context="Context",
        prompt={"system": "s", "user": "u"},
    )
    payload = result.model_dump()
    assert payload["pass_id"] == "doc:mechanical"
    roundtrip = PassResult(**payload)
    assert roundtrip.citations[0].chunk_id == "doc:c1"


def test_manifest_merges_pass_paths() -> None:
    """Manifest can be updated with additional passes."""

    manifest = PassManifest(doc_id="doc", passes={"mechanical": "a.json"})
    manifest.passes["software"] = "b.json"
    payload = manifest.model_dump()
    assert payload["passes"]["software"] == "b.json"


def test_normalized_manifest_defaults() -> None:
    """Normalized manifest captures metadata for auditing."""

    manifest = NormalizedManifest(
        doc_id="doc",
        normalized_path="normalize.json",
        manifest_path="manifest.json",
        checksum="abc",
    )
    assert isinstance(manifest.created_at, datetime)
    assert manifest.block_count == 0
