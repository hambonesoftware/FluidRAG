"""Reranker implementations for late-interaction and cross-encoder scoring."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .utils import normalize_scores, tokenize, vectorize_tokens


@dataclass
class RerankerConfig:
    type: str = "colbert"
    cross_encoder_model: str = "cross-encoder/msmarco-MiniLM-L6"
    cache_ttl_sec: int = 7200


class BaseReranker:
    def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        raise NotImplementedError


class ColbertReranker(BaseReranker):
    """Lightweight late-interaction reranker approximating ColBERT behaviour."""

    def __init__(self, config: RerankerConfig | Dict[str, Any] | None = None) -> None:
        if isinstance(config, dict):
            self.config = RerankerConfig(**config)
        else:
            self.config = config or RerankerConfig()
        self._cache: Dict[Tuple[str, str], float] = {}

    def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        query_tokens = tokenize(query)
        query_vecs = {token: vectorize_tokens([token]) for token in query_tokens}
        scored: List[Tuple[str, float]] = []
        for candidate in candidates:
            chunk_id = candidate["chunk_id"]
            cache_key = (hashlib.sha1(query.lower().encode()).hexdigest(), chunk_id)
            if cache_key in self._cache:
                score = self._cache[cache_key]
            else:
                chunk_tokens = tokenize(candidate["chunk"]["text"])
                chunk_vecs = {token: vectorize_tokens([token]) for token in chunk_tokens}
                score = 0.0
                for token, q_vec in query_vecs.items():
                    max_sim = 0.0
                    for c_token, c_vec in chunk_vecs.items():
                        dot = sum(a * b for a, b in zip(q_vec, c_vec))
                        if dot > max_sim:
                            max_sim = dot
                    score += max_sim
                self._cache[cache_key] = score
            candidate["rerank_score"] = score
            scored.append((chunk_id, score))
        norm = normalize_scores({cid: score for cid, score in scored})
        for candidate in candidates:
            candidate["rerank_score"] = norm.get(candidate["chunk_id"], 0.0)
        return sorted(candidates, key=lambda item: item["rerank_score"], reverse=True)


class CrossEncoderReranker(BaseReranker):
    """Stub cross-encoder reranker that approximates pair scoring via cosine similarity."""

    def __init__(self, config: RerankerConfig | Dict[str, Any] | None = None) -> None:
        if isinstance(config, dict):
            self.config = RerankerConfig(**config)
        else:
            self.config = config or RerankerConfig(type="cross_encoder")
        self._cache: Dict[Tuple[str, str], float] = {}

    def rerank(self, query: str, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        query_vec = vectorize_tokens(tokenize(query))
        scored: List[Tuple[str, float]] = []
        for candidate in candidates:
            chunk_id = candidate["chunk_id"]
            cache_key = (hashlib.sha1(query.lower().encode()).hexdigest(), chunk_id)
            if cache_key in self._cache:
                score = self._cache[cache_key]
            else:
                text_vec = vectorize_tokens(tokenize(candidate["chunk"]["text"]))
                dot = sum(a * b for a, b in zip(query_vec, text_vec))
                norm_q = math.sqrt(sum(a * a for a in query_vec)) or 1.0
                norm_t = math.sqrt(sum(a * a for a in text_vec)) or 1.0
                score = dot / (norm_q * norm_t)
                self._cache[cache_key] = score
            candidate["rerank_score"] = score
            scored.append((chunk_id, score))
        norm = normalize_scores({cid: score for cid, score in scored})
        for candidate in candidates:
            candidate["rerank_score"] = norm.get(candidate["chunk_id"], 0.0)
        return sorted(candidates, key=lambda item: item["rerank_score"], reverse=True)


def select_reranker(config: Dict[str, Any] | None) -> BaseReranker:
    if not config:
        return ColbertReranker()
    cfg = RerankerConfig(**config)
    if cfg.type.lower() == "cross_encoder":
        return CrossEncoderReranker(cfg)
    return ColbertReranker(cfg)


__all__ = ["ColbertReranker", "CrossEncoderReranker", "select_reranker", "RerankerConfig"]
