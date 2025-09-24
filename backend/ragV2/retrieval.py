"""Hybrid retrieval utilities used by the RAG v2 orchestrator."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .config import CFG
from .types import Chunk

Candidate = Tuple[Chunk, float]
SearchFn = Callable[[str, str, Dict[str, str], int], Iterable[Candidate]]


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
        ordered = sorted(ranked.values(), key=lambda item: item[1], reverse=True)
        return ordered

    def search(
        self, query: str, domain: str, edition_filters: Optional[Dict[str, str]] = None
    ) -> List[Chunk]:
        edition_filters = dict(edition_filters or {})
        expanded_terms = self._expander.expand(query)
        pools: List[List[Candidate]] = []
        for searcher, limit in (
            (self._dense, CFG.k_dense),
            (self._sparse, CFG.k_sparse),
            (self._regex, CFG.k_regex),
        ):
            if searcher is None or limit <= 0:
                continue
            term = " ".join(expanded_terms)
            candidates = _as_candidates(searcher(term, domain, edition_filters, limit))
            pools.append(candidates)
        merged = self._merge(pools)
        filtered = self._filter_by_edition(merged, edition_filters)
        diversified = self._diversify(filtered, self._section_diversity)
        ordered_chunks = [chunk for chunk, _score in diversified]
        for idx, chunk in enumerate(ordered_chunks):
            chunk.meta.setdefault("retrieval_rank", idx)
        return ordered_chunks
