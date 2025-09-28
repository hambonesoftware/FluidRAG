"""Vector and sparse retrieval adapters."""
from __future__ import annotations

import math
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence

from backend.app.config import settings
from backend.app.util.logging import get_logger

logger = get_logger(__name__)


def _tokenize(text: str) -> List[str]:
    return [tok.lower() for tok in text.split() if tok.strip()]


@dataclass
class BM25Index:
    """In-memory BM25 index."""

    k1: float = 1.5
    b: float = 0.75

    def __post_init__(self) -> None:
        self._documents: Dict[str, Counter[str]] = {}
        self._doc_lengths: Dict[str, int] = {}
        self._inverted: Dict[str, int] = defaultdict(int)

    def add(self, doc_id: str, text: str) -> None:
        tokens = Counter(_tokenize(text))
        self._documents[doc_id] = tokens
        self._doc_lengths[doc_id] = sum(tokens.values())
        for token in tokens:
            self._inverted[token] += 1

    def _idf(self, term: str) -> float:
        n_docs = len(self._documents) + 1e-9
        doc_freq = self._inverted.get(term, 0) + 1e-9
        return math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)

    def search(self, query: str, limit: int = 10) -> List[dict]:
        tokens = _tokenize(query)
        scores: Dict[str, float] = defaultdict(float)
        avgdl = sum(self._doc_lengths.values()) / (len(self._doc_lengths) or 1)
        for token in tokens:
            idf = self._idf(token)
            for doc_id, doc_tokens in self._documents.items():
                freq = doc_tokens.get(token, 0)
                if freq == 0:
                    continue
                numer = freq * (self.k1 + 1)
                denom = freq + self.k1 * (1 - self.b + self.b * (self._doc_lengths[doc_id] / (avgdl or 1)))
                scores[doc_id] += idf * numer / (denom or 1e-9)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]
        return [{"doc_id": doc_id, "score": score} for doc_id, score in ranked]


class FaissIndex:
    """FAISS wrapper with graceful degradation."""

    def __init__(self, dimension: int) -> None:
        try:
            import faiss  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("faiss is not installed") from exc
        self._faiss = faiss
        self._dimension = dimension
        self._index = faiss.IndexFlatIP(dimension)
        self._ids: List[str] = []

    def add(self, doc_id: str, vector: Sequence[float]) -> None:
        import numpy as np

        arr = np.array([vector], dtype="float32")
        if arr.shape[1] != self._dimension:
            raise ValueError("Vector dimension mismatch")
        self._index.add(arr)
        self._ids.append(doc_id)

    def search(self, query_vec: Sequence[float], k: int = 20) -> List[dict]:
        import numpy as np

        arr = np.array([query_vec], dtype="float32")
        scores, indices = self._index.search(arr, k)
        hits: List[dict] = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < 0 or idx >= len(self._ids):
                continue
            hits.append({"doc_id": self._ids[idx], "score": float(score)})
        return hits

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._faiss.write_index(self._index, str(path))


class QdrantIndex:
    """Qdrant client adapter."""

    def __init__(self, collection: str, dimension: int) -> None:
        try:
            from qdrant_client import QdrantClient  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("qdrant-client is not installed") from exc
        self._client = QdrantClient(path=str(settings.storage_dir / "qdrant.db"))
        self._collection = collection
        self._dimension = dimension
        self._client.recreate_collection(
            collection_name=collection,
            vector_size=dimension,
            distance="Cosine",
        )

    def add(self, vectors: List[List[float]], payloads: List[dict] | None = None) -> None:
        payloads = payloads or [{} for _ in vectors]
        points = []
        for vector, payload in zip(vectors, payloads):
            point_id = payload.get("id") or str(uuid.uuid4())
            points.append({"id": point_id, "vector": vector, "payload": payload})
        self._client.upsert(collection_name=self._collection, points=points)

    def search(self, query_vec: List[float], k: int = 20) -> List[dict]:
        results = self._client.search(
            collection_name=self._collection,
            query_vector=query_vec,
            limit=k,
        )
        return [
            {"doc_id": hit.payload.get("doc_id") or hit.id, "score": float(hit.score)}
            for hit in results
        ]


def hybrid_search(
    bm25: BM25Index | None,
    dense: FaissIndex | QdrantIndex | None,
    query: str,
    query_vec: List[float] | None,
    *,
    alpha: float = 0.5,
    k: int = 20,
) -> List[dict]:
    """Fuse sparse+dense scores."""

    sparse_hits: Dict[str, float] = {}
    if bm25:
        for hit in bm25.search(query, limit=k * 2):
            sparse_hits[hit["doc_id"]] = hit["score"]

    dense_hits: Dict[str, float] = {}
    if dense and query_vec is not None:
        for hit in dense.search(query_vec, k=k * 2):
            dense_hits[hit["doc_id"]] = hit["score"]

    doc_ids = set(sparse_hits) | set(dense_hits)
    fused = []
    for doc_id in doc_ids:
        sparse = sparse_hits.get(doc_id, 0.0)
        dense_score = dense_hits.get(doc_id, 0.0)
        score = alpha * sparse + (1 - alpha) * dense_score
        fused.append({"doc_id": doc_id, "score": score})

    fused.sort(key=lambda item: item["score"], reverse=True)
    return fused[:k]
