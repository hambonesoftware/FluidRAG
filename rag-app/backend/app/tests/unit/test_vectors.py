"""Tests for vector adapter utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from ...adapters.vectors import (
    BM25Index,
    FaissIndex,
    QdrantIndex,
    hybrid_search,
)
from ...config import get_settings


def test_bm25_index_add_and_search() -> None:
    index = BM25Index()
    index.add(["Fluid dynamics handbook"])
    index.add(["control control systems"])
    index.add(["control theory"])

    results = index.search("control", k=3)
    assert results[0][0] == 1  # document with two matches ranks highest
    assert results[0][1] >= results[1][1] > 0


def test_bm25_empty_index_returns_empty() -> None:
    index = BM25Index()
    assert index.search("anything") == []


def test_faiss_index_add_search_and_persist(tmp_path: Path) -> None:
    index_path = tmp_path / "vectors.json"
    index = FaissIndex(dim=3, index_path=str(index_path))
    index.add([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    index.save()

    # Reload and ensure vectors persisted
    reloaded = FaissIndex(dim=3, index_path=str(index_path))
    results = reloaded.search([1.0, 0.0, 0.0], k=1)
    assert results == [(0, pytest.approx(1.0))]


def test_faiss_index_validates_dimensions() -> None:
    index = FaissIndex(dim=2)
    with pytest.raises(ValueError):
        index.add([[1.0, 2.0, 3.0]])
    with pytest.raises(ValueError):
        index.search([1.0, 2.0, 3.0])


def test_qdrant_index_add_and_search(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLUIDRAG_OFFLINE", "false")
    get_settings.cache_clear()
    index = QdrantIndex("test")
    get_settings.cache_clear()

    index.add([[1.0, 0.0], [0.0, 1.0]], payloads=[{"id": "a"}, {"id": "b"}])
    results = index.search([1.0, 0.0], k=2)
    assert results[0]["payload"]["id"] == "a"
    assert 0.0 <= results[0]["score"] <= 1.0


def test_qdrant_index_requires_matching_payloads() -> None:
    index = QdrantIndex("mismatch")
    with pytest.raises(ValueError):
        index.add([[1.0, 0.0], [0.0, 1.0]], payloads=[{}])


def test_qdrant_search_handles_missing_payloads() -> None:
    index = QdrantIndex("partial")
    index.add([[1.0, 0.0], [0.0, 1.0]], payloads=[{"id": "only"}, {}])
    # Deliberately drop one payload to cover fallback branch
    index._payloads.pop()
    results = index.search([0.0, 1.0], k=2)
    assert results[0]["payload"].get("id", "") in {"only", ""}


def test_hybrid_search_with_faiss_and_bm25() -> None:
    bm25 = BM25Index()
    bm25.add(["fluid dynamics", "control systems"])

    faiss = FaissIndex(dim=2)
    faiss.add([[1.0, 0.0], [0.2, 0.8]])

    results = hybrid_search(bm25, faiss, "control", [0.2, 0.8], alpha=0.6, k=2)
    assert len(results) == 2
    assert results[0]["score"] >= results[1]["score"]


def test_hybrid_search_with_qdrant_only() -> None:
    qdrant = QdrantIndex("hybrid")
    qdrant.add([[0.0, 1.0], [1.0, 0.0]], payloads=[{"label": "dense"}, {}])

    results = hybrid_search(None, qdrant, "unused", [1.0, 0.0], alpha=1.0, k=1)
    assert results == [
        {
            "id": 1,
            "score": pytest.approx(1.0),
            "dense": pytest.approx(1.0),
            "sparse": 0.0,
        }
    ]
