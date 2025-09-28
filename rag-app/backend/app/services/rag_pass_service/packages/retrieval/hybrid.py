"""Hybrid retrieval helper."""
from __future__ import annotations

from typing import Dict, List, Tuple

from backend.app.adapters.vectors import BM25Index, EmbeddingModel, hybrid_search


def retrieve_ranked(
    *,
    query: str,
    chunk_texts: Dict[str, str],
    embeddings: Dict[str, List[float]],
    limit: int = 5,
) -> List[Tuple[str, float]]:
    """Return ranked chunk identifiers paired with hybrid relevance scores."""

    bm25 = BM25Index()
    for chunk_id, text in chunk_texts.items():
        bm25.add(chunk_id, text)
    embedder = EmbeddingModel()
    return hybrid_search(bm25, embeddings, query, embedder=embedder, limit=limit)
