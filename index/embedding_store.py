"""Lightweight embedding store backed by Parquet for microchunks."""
from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from ingest.microchunker import MicroChunk


class EmbeddingStore:
    """Persist and query embedding vectors for microchunks."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.vectorizer_path = self.path.with_suffix(".vectorizer.pkl")
        self._df: Optional[pd.DataFrame] = None
        self._vectorizer: Optional[TfidfVectorizer] = None

    # ------------------------------------------------------------------
    # Loading / persistence helpers
    # ------------------------------------------------------------------
    def load(self) -> None:
        if self._df is not None:
            return
        if self.path.exists():
            self._df = pd.read_parquet(self.path)
        else:
            self._df = pd.DataFrame(columns=["micro_id", "doc_id", "content_hash", "vector"])
        if self.vectorizer_path.exists():
            with self.vectorizer_path.open("rb") as handle:
                self._vectorizer = pickle.load(handle)

    def save(self) -> None:
        if self._df is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._df.to_parquet(self.path, index=False)
        if self._vectorizer is not None:
            with self.vectorizer_path.open("wb") as handle:
                pickle.dump(self._vectorizer, handle)

    # ------------------------------------------------------------------
    # Index construction
    # ------------------------------------------------------------------
    def build(self, microchunks: Sequence[MicroChunk], *, vectorizer: Optional[TfidfVectorizer] = None) -> None:
        """Construct a fresh embedding index from ``microchunks``."""

        self.load()
        texts: List[str] = []
        ids: List[str] = []
        doc_ids: List[str] = []
        hashes: List[str] = []
        for micro in microchunks:
            text = micro.get("norm_text") or micro.get("text") or ""
            texts.append(text)
            ids.append(micro["micro_id"])
            doc_ids.append(micro.get("doc_id", "doc-unknown"))
            hashes.append(hashlib.sha1(text.encode("utf-8")).hexdigest())

        if vectorizer is None:
            vectorizer = TfidfVectorizer(min_df=1, ngram_range=(1, 2))
            matrix = vectorizer.fit_transform(texts)
        else:
            matrix = vectorizer.transform(texts)
        vectors = matrix.toarray().astype(np.float32)

        self._df = pd.DataFrame(
            {
                "micro_id": ids,
                "doc_id": doc_ids,
                "content_hash": hashes,
                "vector": [vec.tolist() for vec in vectors],
            }
        )
        self._vectorizer = vectorizer
        self.save()

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def vector(self, micro_id: str) -> Optional[np.ndarray]:
        self.load()
        if self._df is None:
            return None
        row = self._df.loc[self._df["micro_id"] == micro_id]
        if row.empty:
            return None
        vector = row.iloc[0]["vector"]
        return np.asarray(vector, dtype=np.float32)

    def batch_vectors(self, micro_ids: Sequence[str]) -> List[np.ndarray]:
        return [self.vector(mid) for mid in micro_ids if self.vector(mid) is not None]

    def ensure_vectorizer(self) -> TfidfVectorizer:
        self.load()
        if self._vectorizer is None:
            raise RuntimeError("EmbeddingStore has not been initialised with a vectorizer")
        return self._vectorizer

    def search(self, query: str, k: int = 20) -> List[Tuple[str, float]]:
        """Return the top ``k`` micro_ids ranked by cosine similarity."""

        vectorizer = self.ensure_vectorizer()
        query_vec = vectorizer.transform([query]).toarray().astype(np.float32)[0]
        self.load()
        if self._df is None or self._df.empty:
            return []
        stacked = np.vstack(self._df["vector"].apply(np.asarray).to_numpy())
        norms = np.linalg.norm(stacked, axis=1) * np.linalg.norm(query_vec)
        norms[norms == 0.0] = 1.0
        scores = stacked @ query_vec / norms
        top_idx = np.argsort(scores)[::-1][:k]
        return [
            (self._df.iloc[idx]["micro_id"], float(scores[idx]))
            for idx in top_idx
        ]


__all__ = ["EmbeddingStore"]
