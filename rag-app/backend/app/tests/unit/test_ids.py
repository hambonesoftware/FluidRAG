"""Tests for identifier utilities."""

from __future__ import annotations

import pytest

from ...contracts.ids import make_pass_id, normalize_doc_id, pass_artifact_name


def test_normalize_doc_id_success() -> None:
    assert normalize_doc_id("Doc 123") == "doc-123"
    assert normalize_doc_id("--Complex__Name--") == "complex-name"


def test_normalize_doc_id_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        normalize_doc_id("")
    with pytest.raises(ValueError):
        normalize_doc_id("***")


def test_pass_identifier_helpers() -> None:
    assert pass_artifact_name("Executive Summary") == "executive-summary.json"
    assert make_pass_id("Doc", "Summary") == "doc:summary"
