"""Lightweight BM25 index for lexical microchunk retrieval."""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import regex as re
from rank_bm25 import BM25Okapi

from ingest.microchunker import MicroChunk

_TOKEN_SPLIT = re.compile(r"\p{L}[\p{L}\p{Mn}\p{Mc}\p{Pd}\p{Pc}\p{Nd}]*|\p{N}+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    return [tok.lower() for tok in _TOKEN_SPLIT.findall(text)]


class BM25Store:
    """Wrapper around :class:`rank_bm25.BM25Okapi` with persistence."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._bm25: Optional[BM25Okapi] = None
        self._micro_ids: List[str] = []

    def load(self) -> None:
        if self._bm25 is not None:
            return
        if not self.path.exists():
            return
        with self.path.open("rb") as handle:
            payload = pickle.load(handle)
        self._bm25 = payload["bm25"]
        self._micro_ids = payload["micro_ids"]

    def save(self) -> None:
        if self._bm25 is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"bm25": self._bm25, "micro_ids": self._micro_ids}
        with self.path.open("wb") as handle:
            pickle.dump(payload, handle)

    def build(self, microchunks: Sequence[MicroChunk]) -> None:
        docs = []
        ids = []
        for micro in microchunks:
            text = micro.get("norm_text") or micro.get("text") or ""
            docs.append(_tokenize(text))
            ids.append(micro["micro_id"])
        if not docs:
            self._bm25 = None
            self._micro_ids = []
            return
        self._bm25 = BM25Okapi(docs)
        self._micro_ids = ids
        self.save()

    def search(self, query: str, k: int = 20) -> List[Tuple[str, float]]:
        self.load()
        if self._bm25 is None:
            return []
        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)
        order = scores.argsort()[::-1][:k]
        return [(self._micro_ids[idx], float(scores[idx])) for idx in order]


__all__ = ["BM25Store"]
