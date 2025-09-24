"""Cross-encoder and LLM based reranking utilities."""
from __future__ import annotations

from typing import Callable, Iterable, List, Optional

from .types import Chunk

ScoreFn = Callable[[str, Chunk], float]


class Reranker:
    """Simple reranker wrapper that keeps meta-data about scores."""

    def __init__(self, scorer: Optional[ScoreFn] = None, top_k: Optional[int] = None) -> None:
        self._scorer = scorer
        self._top_k = top_k

    def rerank(self, query: str, candidates: Iterable[Chunk]) -> List[Chunk]:
        chunks = list(candidates or [])
        if not self._scorer or not chunks:
            return chunks
        scored = []
        for chunk in chunks:
            score = float(self._scorer(query, chunk))
            chunk.meta.setdefault("crossenc_score", score)
            scored.append((chunk, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        if self._top_k is not None and self._top_k > 0:
            scored = scored[: self._top_k]
        return [chunk for chunk, _score in scored]
