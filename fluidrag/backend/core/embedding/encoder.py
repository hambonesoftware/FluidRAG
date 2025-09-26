"""Embedding encoder stubs used by the refactor scaffolding."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

import hashlib

import numpy as np


@dataclass
class EmbeddingEncoder:
    """Light-weight wrapper returning deterministic placeholder embeddings.

    The real system will replace this stub with an inference client. For the
    scaffolding we return pseudo-random unit vectors seeded by the text content
    so that tests can exercise downstream indexing deterministically.
    """

    model_name: str = "gte-base@v3"
    dim: int = 768
    seed: int = 13

    def embed_texts(self, texts: Iterable[str]) -> np.ndarray:
        texts_list: List[str] = list(texts)
        if not texts_list:
            return np.empty((0, self.dim), dtype=np.float32)

        vectors = np.empty((len(texts_list), self.dim), dtype=np.float32)
        for idx, text in enumerate(texts_list):
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            seed_seq = np.frombuffer(digest[:16], dtype=np.uint32)
            local_rng = np.random.default_rng(seed_seq)
            vec = local_rng.normal(size=self.dim)
            vec_norm = np.linalg.norm(vec)
            if vec_norm == 0:
                vec = np.zeros(self.dim, dtype=np.float32)
            else:
                vec = (vec / vec_norm).astype(np.float32)
            vectors[idx] = vec
        return vectors


__all__ = ["EmbeddingEncoder"]
