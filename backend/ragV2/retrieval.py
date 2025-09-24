"""Hybrid retrieval utilities used by the RAG v2 orchestrator."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .config import CFG
from .types import Chunk

Candidate = Tuple[Chunk, float]
SearchFn = Callable[[str, str, Dict[str, str], int], Iterable[Candidate]]
HydeFn = Callable[[str], Sequence[str]]
LateInteractionFn = Callable[[str, Chunk], float]
CrossEncoderFn = Callable[[str, Chunk], float]


@dataclass
class QueryExpansion:
    """Lightweight expander used to surface acronyms or units present in the query."""

    expansions: Dict[str, Sequence[str]]

    def expand(self, query: str) -> List[str]:
        tokens = [token.strip() for token in query.split() if token.strip()]
        results = set(tokens)
        for token in tokens:
            key = token.lower()
            if key in self.expansions:
                for value in self.expansions[key]:
                    results.add(value)
        return list(results)


def _as_candidates(items: Iterable[Candidate | Chunk]) -> List[Candidate]:
    normalized: List[Candidate] = []
    for item in items or []:
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], (int, float)):
            chunk, score = item
        else:
            chunk, score = item, 1.0  # type: ignore[assignment]
        if not isinstance(chunk, Chunk):
            continue
        normalized.append((chunk, float(score)))
    return normalized


class Retriever:
    """Hybrid retriever that combines dense, sparse and regex driven candidates."""

    def __init__(
        self,
        *,
        dense_search: Optional[SearchFn] = None,
        sparse_search: Optional[SearchFn] = None,
        regex_search: Optional[SearchFn] = None,
        query_expander: Optional[QueryExpansion] = None,
        section_diversity: Optional[int] = None,
        hyde_generator: Optional[HydeFn] = None,
        colbert_scorer: Optional[LateInteractionFn] = None,
        cross_encoder: Optional[CrossEncoderFn] = None,
    ) -> None:
        self._dense = dense_search
        self._sparse = sparse_search
        self._regex = regex_search
        self._expander = query_expander or QueryExpansion({})
        self._section_diversity = (
            int(section_diversity)
            if section_diversity is not None
            else CFG.section_diversity
        )
        self._hyde_generator = hyde_generator
        self._colbert_scorer = colbert_scorer
        self._cross_encoder = cross_encoder

    def _filter_by_edition(
        self, candidates: List[Candidate], filters: Dict[str, str]
    ) -> List[Candidate]:
        if not filters:
            return candidates
        result: List[Candidate] = []
        for chunk, score in candidates:
            meta = chunk.meta or {}
            edition_map = meta.get("editions")
            jurisdiction = meta.get("jurisdiction")
            if filters.get("jurisdiction") and jurisdiction:
                if jurisdiction != filters["jurisdiction"]:
                    continue
            if isinstance(edition_map, dict):
                skip = False
                for key, desired in filters.items():
                    if key == "jurisdiction":
                        continue
                    have = edition_map.get(key)
                    if have is not None and desired and have != desired:
                        skip = True
                        break
                if skip:
                    continue
            result.append((chunk, score))
        return result

    @staticmethod
    def _diversify(candidates: List[Candidate], limit: int) -> List[Candidate]:
        if limit <= 0:
            return candidates
        seen_per_section: Dict[Tuple[str, Optional[str]], int] = defaultdict(int)
        diversified: List[Candidate] = []
        for chunk, score in candidates:
            key = (chunk.doc_id, chunk.section_no)
            if seen_per_section[key] >= limit:
                continue
            diversified.append((chunk, score))
            seen_per_section[key] += 1
        return diversified

    def _merge(self, pools: Sequence[List[Candidate]]) -> List[Candidate]:
        ranked: Dict[str, Tuple[Chunk, float]] = {}
        for priority, pool in enumerate(pools):
            for chunk, score in pool:
                existing = ranked.get(chunk.chunk_id)
                boost = 1.0 + (0.05 * (len(pools) - priority))
                composite = float(score) * boost
                if existing is None or composite > existing[1]:
                    ranked[chunk.chunk_id] = (chunk, composite)
                # persist per-stage retrieval scores for transparency
                stage = chunk.stage_tag or chunk.meta.get("stage_tag") or "STANDARD"
                chunk.retrieval_scores.setdefault(stage, 0.0)
                chunk.retrieval_scores[stage] = max(chunk.retrieval_scores[stage], float(score))
        ordered = sorted(ranked.values(), key=lambda item: item[1], reverse=True)
        return ordered

    def _hyde_candidates(
        self,
        query: str,
        domain: str,
        filters: Dict[str, str],
        base_pool: List[Candidate],
    ) -> List[Candidate]:
        if not CFG.enable_hyde or self._dense is None:
            return []
        if len(base_pool) >= CFG.hyde_sparse_min_hits and len(query) > CFG.query_short_chars:
            return []
        prompts = [query]
        if self._hyde_generator is not None:
            try:
                prompts = list(self._hyde_generator(query)) or [query]
            except Exception:
                prompts = [query]
        prompts = prompts[: max(1, CFG.hyde_hypotheses)]
        hyde_pool: List[Candidate] = []
        for prompt in prompts:
            hyde_hits = _as_candidates(self._dense(prompt, domain, filters, CFG.k_dense))
            hyde_pool.extend(hyde_hits)
        return hyde_pool

    def _apply_colbert(self, query: str, pool: List[Candidate]) -> List[Candidate]:
        if not CFG.enable_colbert or self._colbert_scorer is None:
            return pool
        rescored: List[Candidate] = []
        for chunk, score in pool:
            try:
                colbert_score = float(self._colbert_scorer(query, chunk))
            except Exception:
                colbert_score = 0.0
            chunk.meta.setdefault("colbert_score", colbert_score)
            chunk.retrieval_scores.setdefault(chunk.stage_tag, colbert_score)
            rescored.append((chunk, 0.7 * score + 0.3 * colbert_score))
        rescored.sort(key=lambda item: item[1], reverse=True)
        return rescored[:CFG.k_colbert]

    def _apply_cross_encoder(self, query: str, pool: List[Candidate]) -> List[Candidate]:
        if not CFG.enable_cross_encoder or self._cross_encoder is None:
            return pool
        top = pool[: CFG.cross_encoder_top_k]
        rescored: List[Candidate] = []
        for chunk, score in top:
            try:
                ce_score = float(self._cross_encoder(query, chunk))
            except Exception:
                ce_score = 0.0
            chunk.meta.setdefault("crossenc_score", ce_score)
            rescored.append((chunk, 0.5 * score + 0.5 * ce_score))
        rescored.sort(key=lambda item: item[1], reverse=True)
        return rescored

    def search(
        self, query: str, domain: str, edition_filters: Optional[Dict[str, str]] = None
    ) -> List[Chunk]:
        edition_filters = dict(edition_filters or {})
        expanded_terms = self._expander.expand(query)
        pools: List[List[Candidate]] = []

        sparse_hits: List[Candidate] = []
        if self._sparse is not None and CFG.k_sparse > 0:
            term = " ".join(expanded_terms)
            sparse_hits = _as_candidates(self._sparse(term, domain, edition_filters, CFG.k_sparse))
            pools.append(sparse_hits)

        dense_hits: List[Candidate] = []
        if self._dense is not None and CFG.k_dense > 0:
            dense_hits = _as_candidates(self._dense(query, domain, edition_filters, CFG.k_dense))
            pools.append(dense_hits)

        hyde_hits = self._hyde_candidates(query, domain, edition_filters, sparse_hits)
        if hyde_hits:
            pools.append(hyde_hits)

        if self._regex is not None and CFG.k_regex > 0:
            term = " ".join(expanded_terms)
            regex_hits = _as_candidates(self._regex(term, domain, edition_filters, CFG.k_regex))
            pools.append(regex_hits)

        merged = self._merge(pools)
        merged = self._apply_colbert(query, merged)
        merged = self._apply_cross_encoder(query, merged)

        filtered = self._filter_by_edition(merged, edition_filters)
        diversified = self._diversify(filtered, self._section_diversity)
        ordered_chunks = [chunk for chunk, _score in diversified]
        for idx, chunk in enumerate(ordered_chunks):
            if chunk.meta.get("stage_tag"):
                chunk.stage_tag = str(chunk.meta.get("stage_tag")).upper()
            chunk.meta.setdefault("retrieval_rank", idx)
            chunk.retrieval_scores.setdefault(chunk.stage_tag, float(len(ordered_chunks) - idx))
        return ordered_chunks
