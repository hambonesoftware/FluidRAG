"""Local vector search support."""
from __future__ import annotations

from typing import Dict, List, Tuple

from backend.app.adapters.vectors import BM25Index, EmbeddingModel


def build_local_index(chunks: Dict[str, str]) -> Tuple[BM25Index, Dict[str, List[float]]]:
    bm25 = BM25Index()
    embedder = EmbeddingModel()
    for chunk_id, text in chunks.items():
        bm25.add(chunk_id, text)
    embeddings = {chunk_id: vector for chunk_id, vector in zip(chunks.keys(), embedder.embed_texts(list(chunks.values())))}
    return bm25, embeddings
