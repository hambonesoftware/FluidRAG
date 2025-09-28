"""Hybrid retrieval helpers for pass execution."""

from __future__ import annotations

from typing import Any

from backend.app.adapters import BM25Index, FaissIndex, LLMClient, hybrid_search
from backend.app.util.logging import get_logger

from ..rank.fluid import flow_score
from ..rank.graph import graph_score
from ..rank.hep import energy_score

logger = get_logger(__name__)


def retrieve_ranked(chunks: list[dict[str, Any]], domain: str) -> list[dict[str, Any]]:
    """Hybrid BM25 + dense + physics scores + graph proximity."""

    if not chunks:
        return []

    texts = [str(chunk.get("text", "")) for chunk in chunks]
    bm25 = BM25Index()
    bm25.add(texts)

    client = LLMClient()
    dense_index: FaissIndex | None = None
    embeddings = client.embed(texts) if texts else []
    if embeddings:
        dense_index = FaissIndex(len(embeddings[0]))
        dense_index.add(embeddings)
    query = f"{domain} engineering insights"
    query_vec = client.embed([query])[0] if embeddings else None
    fused = hybrid_search(
        bm25,
        dense_index,
        query=query,
        query_vec=query_vec,
        k=min(len(chunks), 12),
    )

    ranked: list[dict[str, Any]] = []
    for row in fused:
        idx = int(row["id"])
        chunk = dict(chunks[idx])
        chunk["sparse_score"] = float(row.get("sparse", 0.0))
        chunk["dense_score"] = float(row.get("dense", 0.0))
        chunk["score"] = float(row.get("score", 0.0))
        chunk["flow_score"] = flow_score(chunk)
        chunk["energy_score"] = energy_score(chunk)
        chunk["graph_score"] = graph_score(chunk)
        chunk["total_score"] = (
            chunk["score"]
            + 0.3 * chunk["flow_score"]
            + 0.2 * chunk["energy_score"]
            + 0.1 * chunk["graph_score"]
        )
        ranked.append(chunk)

    ranked.sort(key=lambda item: item.get("total_score", 0.0), reverse=True)
    logger.debug(
        "retrieval.rank",
        extra={"domain": domain, "candidates": len(ranked)},
    )
    return ranked


__all__ = ["retrieve_ranked"]
