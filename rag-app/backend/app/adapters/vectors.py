"""Vector search utilities."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple


def _tokenize(text: str) -> List[str]:
    return [tok.lower() for tok in text.split() if tok.strip()]


@dataclass
class EmbeddingModel:
    dimension: int = 64

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        import hashlib

        embeddings: List[List[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            floats = [b / 255.0 for b in digest[: self.dimension]]
            if len(floats) < self.dimension:
                floats.extend([0.0] * (self.dimension - len(floats)))
            embeddings.append(floats)
        return embeddings


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.documents: Dict[str, Counter[str]] = {}
        self.doc_lengths: Dict[str, int] = {}
        self.inverted_index: Dict[str, int] = defaultdict(int)

    def add(self, doc_id: str, text: str) -> None:
        tokens = Counter(_tokenize(text))
        self.documents[doc_id] = tokens
        length = sum(tokens.values())
        self.doc_lengths[doc_id] = length
        for token in tokens:
            self.inverted_index[token] += 1

    def _idf(self, term: str) -> float:
        n_docs = len(self.documents) + 1e-9
        doc_freq = self.inverted_index.get(term, 0) + 1e-9
        return math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)

    def search(self, query: str, limit: int = 5) -> List[Tuple[str, float]]:
        query_tokens = _tokenize(query)
        scores: Dict[str, float] = defaultdict(float)
        avgdl = sum(self.doc_lengths.values()) / (len(self.doc_lengths) or 1)
        for term in query_tokens:
            idf = self._idf(term)
            for doc_id, tokens in self.documents.items():
                freq = tokens.get(term, 0)
                if freq == 0:
                    continue
                score = idf * (freq * (self.k1 + 1)) / (
                    freq + self.k1 * (1 - self.b + self.b * (self.doc_lengths[doc_id] / (avgdl or 1)))
                )
                scores[doc_id] += score
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]


class FaissIndex:
    def __init__(self, dimension: int) -> None:
        try:
            import faiss  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("faiss is not installed") from exc
        self.faiss = faiss
        self.dimension = dimension
        self.index = faiss.IndexFlatIP(dimension)
        self.ids: List[str] = []

    def add(self, doc_id: str, vector: Sequence[float]) -> None:
        import numpy as np

        arr = np.array([vector], dtype="float32")
        self.index.add(arr)
        self.ids.append(doc_id)

    def search(self, query: Sequence[float], limit: int = 5) -> List[Tuple[str, float]]:
        import numpy as np

        arr = np.array([query], dtype="float32")
        scores, idxs = self.index.search(arr, limit)
        hits: List[Tuple[str, float]] = []
        for idx, score in zip(idxs[0], scores[0]):
            if idx < 0 or idx >= len(self.ids):
                continue
            hits.append((self.ids[idx], float(score)))
        return hits

    def save(self, path: str) -> None:
        self.faiss.write_index(self.index, path)


class QdrantIndex:
    def __init__(self, collection: str, dimension: int) -> None:
        try:
            from qdrant_client import QdrantClient  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("qdrant-client is not installed") from exc
        self.client = QdrantClient(path="./qdrant.db")
        self.collection = collection
        self.dimension = dimension
        self.client.recreate_collection(collection_name=collection, vector_size=dimension, distance="Cosine")

    def add(self, doc_id: str, vector: Sequence[float]) -> None:
        self.client.upsert(
            collection_name=self.collection,
            points=[{"id": doc_id, "vector": list(vector), "payload": {"doc_id": doc_id}}],
        )

    def search(self, query: Sequence[float], limit: int = 5) -> List[Tuple[str, float]]:
        results = self.client.search(
            collection_name=self.collection,
            query_vector=list(query),
            limit=limit,
        )
        return [(point.payload["doc_id"], float(point.score)) for point in results]


def hybrid_search(
    bm25: BM25Index,
    embeddings: Dict[str, List[float]],
    query: str,
    *,
    embedder: EmbeddingModel,
    alpha: float = 0.5,
    limit: int = 5,
) -> List[Tuple[str, float]]:
    bm25_hits = bm25.search(query, limit=limit * 2)
    query_vec = embedder.embed_texts([query])[0]

    def cosine(a: Sequence[float], b: Sequence[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a)) + 1e-9
        norm_b = math.sqrt(sum(x * x for x in b)) + 1e-9
        return dot / (norm_a * norm_b)

    dense_scores = {doc_id: cosine(query_vec, embeddings.get(doc_id, [])) for doc_id, _ in bm25_hits}
    blended = []
    for doc_id, sparse_score in bm25_hits:
        dense_score = dense_scores.get(doc_id, 0.0)
        score = alpha * sparse_score + (1 - alpha) * dense_score
        blended.append((doc_id, score))
    return sorted(blended, key=lambda item: item[1], reverse=True)[:limit]
