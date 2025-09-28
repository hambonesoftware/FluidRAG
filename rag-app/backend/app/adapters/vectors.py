"""Vector adapters and lightweight retrieval utilities."""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..util.logging import get_logger

logger = get_logger(__name__)


def _tokenize(text: str) -> list[str]:
    """Lowercase whitespace tokenizer used for sparse retrieval."""
    return [token for token in text.lower().split() if token]


class EmbeddingModel(ABC):
    """Abstraction for embedding backends."""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch embed texts."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return embedding dimensionality."""


class BM25Index:
    """Sparse BM25 index over chunks."""

    def __init__(self) -> None:
        """Init BM25 index."""
        self._doc_freqs: dict[str, int] = {}
        self._documents: list[list[str]] = []
        self._doc_lengths: list[int] = []
        self._avgdl: float = 0.0
        self._k1 = 1.5
        self._b = 0.75

    def add(self, docs: list[str]) -> None:
        """Add docs."""
        for doc in docs:
            tokens = _tokenize(doc)
            self._documents.append(tokens)
            self._doc_lengths.append(len(tokens))
            for token in set(tokens):
                self._doc_freqs[token] = self._doc_freqs.get(token, 0) + 1
        total_len = sum(self._doc_lengths) or 1
        self._avgdl = total_len / max(len(self._documents), 1)
        logger.debug(
            "bm25.add", extra={"docs": len(docs), "total_docs": len(self._documents)}
        )

    def _idf(self, term: str) -> float:
        df = self._doc_freqs.get(term, 0)
        if df == 0:
            return 0.0
        n = len(self._documents)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int = 20) -> list[tuple[int, float]]:
        """Search top-k."""
        if not self._documents:
            return []
        query_tokens = _tokenize(query)
        scores: list[tuple[int, float]] = []
        for idx, doc_tokens in enumerate(self._documents):
            score = 0.0
            freq: dict[str, int] = {}
            for token in doc_tokens:
                freq[token] = freq.get(token, 0) + 1
            for token in query_tokens:
                if token not in freq:
                    continue
                tf = freq[token]
                numerator = tf * (self._k1 + 1)
                denominator = tf + self._k1 * (
                    1
                    - self._b
                    + self._b * (self._doc_lengths[idx] / (self._avgdl or 1))
                )
                score += self._idf(token) * (numerator / (denominator or 1))
            scores.append((idx, score))
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:k]


class FaissIndex:
    """Local FAISS dense vector index."""

    def __init__(self, dim: int, index_path: str | None = None) -> None:
        """Create or load index."""
        self._dim = dim
        self._vectors: list[list[float]] = []
        self._path = Path(index_path) if index_path else None
        if self._path and self._path.exists():
            try:
                payload = json.loads(self._path.read_text(encoding="utf-8"))
                self._vectors = [
                    [float(value) for value in vector]
                    for vector in payload.get("vectors", [])
                ]
            except Exception as exc:  # noqa: BLE001
                logger.warning("faiss.load_failed", extra={"error": str(exc)})
                self._vectors = []

    def _validate(self, vector: Sequence[float]) -> None:
        if len(vector) != self._dim:
            raise ValueError(f"vector dimensionality {len(vector)} != {self._dim}")

    def add(self, vectors: list[list[float]]) -> None:
        """Add vectors."""
        for vector in vectors:
            self._validate(vector)
            self._vectors.append([float(v) for v in vector])
        logger.debug(
            "faiss.add", extra={"count": len(vectors), "total": len(self._vectors)}
        )

    def _cosine(self, a: Sequence[float], b: Sequence[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
        norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
        return dot / (norm_a * norm_b)

    def search(self, query_vec: list[float], k: int = 20) -> list[tuple[int, float]]:
        """Search top-k."""
        self._validate(query_vec)
        scored = [
            (idx, self._cosine(query_vec, vector))
            for idx, vector in enumerate(self._vectors)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:k]

    def save(self) -> None:
        """Persist index."""
        if not self._path:
            return
        data = {"vectors": self._vectors, "dim": self._dim}
        self._path.write_text(json.dumps(data), encoding="utf-8")


class QdrantIndex:
    """Qdrant remote dense vector index."""

    def __init__(self, collection: str) -> None:
        """Init client/collection."""
        self._collection = collection
        self._vectors: list[list[float]] = []
        self._payloads: list[dict[str, Any]] = []
        if get_settings().offline is False:
            logger.warning(
                "qdrant.offline_stub",
                extra={"collection": collection, "mode": "offline"},
            )

    def add(self, vectors: list[list[float]], payloads: list[dict] | None) -> None:
        """Add vectors."""
        self._vectors.extend([list(map(float, vector)) for vector in vectors])
        payloads = payloads or [{} for _ in vectors]
        if len(payloads) != len(vectors):
            raise ValueError("payload count must match vectors")
        self._payloads.extend(payloads)

    def search(self, query_vec: list[float], k: int = 20) -> list[dict]:
        """Search."""
        faiss = FaissIndex(len(query_vec))
        faiss.add(self._vectors)
        results = faiss.search(query_vec, k=k)
        response: list[dict[str, Any]] = []
        for idx, score in results:
            payload = self._payloads[idx] if idx < len(self._payloads) else {}
            response.append({"id": idx, "score": score, "payload": payload})
        return response


def hybrid_search(
    bm25: BM25Index | None,
    dense: FaissIndex | QdrantIndex | None,
    query: str,
    query_vec: list[float] | None,
    alpha: float = 0.5,
    k: int = 20,
) -> list[dict[str, Any]]:
    """Fuse sparse+dense scores"""
    sparse_scores: dict[int, float] = {}
    if bm25 is not None:
        for idx, score in bm25.search(query, k=k):
            if score > 0:
                sparse_scores[idx] = score

    dense_scores: dict[int, float] = {}
    if dense is not None and query_vec is not None:
        if isinstance(dense, FaissIndex):
            faiss_results = dense.search(query_vec, k=k)
            for idx, score in faiss_results:
                dense_scores[idx] = score
        else:
            qdrant_results = dense.search(query_vec, k=k)
            for item in qdrant_results:
                dense_scores[int(item.get("id", 0))] = float(item.get("score", 0.0))

    combined: dict[int, dict[str, float]] = {}
    for idx in set(sparse_scores) | set(dense_scores):
        combined[idx] = {
            "sparse": sparse_scores.get(idx, 0.0),
            "dense": dense_scores.get(idx, 0.0),
        }
    fused: list[tuple[int, float, dict[str, float]]] = []
    for idx, parts in combined.items():
        score = alpha * parts["dense"] + (1 - alpha) * parts["sparse"]
        fused.append((idx, score, parts))
    fused.sort(key=lambda item: item[1], reverse=True)
    top = fused[:k]
    return [
        {"id": idx, "score": score, "dense": parts["dense"], "sparse": parts["sparse"]}
        for idx, score, parts in top
    ]


__all__ = [
    "EmbeddingModel",
    "BM25Index",
    "FaissIndex",
    "QdrantIndex",
    "hybrid_search",
]
