"""Hybrid retrieval pipeline for standards clauses."""
from __future__ import annotations

import math
import re
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from fluidrag.config import load_config

from ..indexes.clause_index import ClauseIndex
from .utils import normalize_scores, tokenize, vectorize_tokens


@dataclass
class RetrievalConfig:
    k_exact: int = 6
    k_sparse: int = 12
    k_dense: int = 16
    k_candidates: int = 24
    k_final: int = 1
    allow_multi_final: bool = False
    hybrid_weights: Dict[str, float] = None
    reranker: Dict[str, Any] = None

    def __post_init__(self) -> None:
        if self.hybrid_weights is None:
            self.hybrid_weights = {"dense": 0.55, "sparse": 0.35, "exact": 0.10}
        if self.reranker is None:
            self.reranker = {"type": "colbert"}


class HybridRetriever:
    """Build sparse/dense indexes and perform hybrid retrieval."""

    CLAUSE_QUERY_RE = re.compile(r"(?i)(?:§|clause\s+)?((?:\d+\.)*\d+[A-Za-z]?)")
    STANDARD_QUERY_RE = re.compile(r"(?i)(ISO|IEC|NFPA|ANSI|OSHA|CFR)\s*[\-:]?\s*([0-9A-Za-z\.\-]+)")

    def __init__(
        self,
        clause_index: ClauseIndex,
        config: Optional[RetrievalConfig | Dict[str, Any]] = None,
        scoring_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        if isinstance(config, dict):
            self.config = RetrievalConfig(**config)
        else:
            self.config = config or RetrievalConfig()
        self.clause_index = clause_index
        self.scoring_config = scoring_config or {}
        self._chunks: Dict[str, Dict[str, Any]] = {}
        self._sparse_vectors: Dict[str, Counter[str]] = {}
        self._dense_vectors: Dict[str, List[float]] = {}
        self._doc_frequency: Counter[str] = Counter()
        self._avg_doc_len: float = 1.0
        self._doc_chunks: Dict[str, List[str]] = defaultdict(list)
        self._macro_children: Dict[str, set[str]] = defaultdict(set)
        self._doc_clause_numbers: Dict[str, set[str]] = defaultdict(set)

    def index(
        self,
        chunks: Sequence[Dict[str, Any]],
        *,
        macro_map: Optional[Dict[str, Iterable[str]]] = None,
    ) -> None:
        for chunk in chunks:
            chunk_id = str(chunk.get("id"))
            self._chunks[chunk_id] = chunk
            doc_id = str(chunk.get("doc_id"))
            self._doc_chunks[doc_id].append(chunk_id)
            hier = chunk.get("hier") or {}
            clause_id = hier.get("clause")
            if clause_id:
                self.clause_index.put(doc_id, clause_id, chunk_id)
                self._doc_clause_numbers[doc_id].add(str(clause_id))
            tokens = tokenize(" ".join([chunk.get("prefix", ""), chunk.get("text", "")]))
            heading = (hier.get("heading") or "").lower().split()
            sparse = Counter(tokens)
            for token in heading:
                sparse[token] += 2
            numeric_tokens = [token for token in tokens if any(ch.isdigit() for ch in token)]
            for token in numeric_tokens:
                sparse[token] += 1
            self._sparse_vectors[chunk_id] = sparse
            for token in sparse:
                self._doc_frequency[token] += 1
            self._dense_vectors[chunk_id] = vectorize_tokens(tokens)
        total_len = sum(sum(vector.values()) for vector in self._sparse_vectors.values())
        self._avg_doc_len = max(1.0, total_len / max(1, len(self._sparse_vectors)))
        if macro_map:
            for macro_id, micro_ids in macro_map.items():
                self._macro_children[str(macro_id)].update(str(mid) for mid in micro_ids)

    def retrieve(
        self,
        query: str,
        *,
        discipline: Optional[str] = None,
        doc_filter: Optional[Iterable[str]] = None,
        macro_filter: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        doc_filter_set = {str(doc) for doc in doc_filter} if doc_filter else None
        macro_filter_set = {str(mid) for mid in macro_filter} if macro_filter else None
        exact_ids = self._exact_clause_hits(query, doc_filter_set)
        sparse_scores = self._sparse_search(query, doc_filter_set, macro_filter_set)
        dense_scores = self._dense_search(query, doc_filter_set, macro_filter_set)
        candidate_ids = OrderedDict()
        for cid in exact_ids[: self.config.k_exact]:
            candidate_ids[cid] = None
        for cid, _ in sparse_scores[: self.config.k_sparse]:
            candidate_ids.setdefault(cid, None)
        for cid, _ in dense_scores[: self.config.k_dense]:
            candidate_ids.setdefault(cid, None)
        candidate_list = list(candidate_ids.keys())[: self.config.k_candidates]
        dense_norm = normalize_scores({cid: score for cid, score in dense_scores})
        sparse_norm = normalize_scores({cid: score for cid, score in sparse_scores})
        exact_norm = {cid: 1.0 for cid in exact_ids}
        results: List[Dict[str, Any]] = []
        for cid in candidate_list:
            chunk = self._chunks.get(cid)
            if not chunk:
                continue
            base = 0.0
            base += self.config.hybrid_weights.get("dense", 0.55) * dense_norm.get(cid, 0.0)
            base += self.config.hybrid_weights.get("sparse", 0.35) * sparse_norm.get(cid, 0.0)
            base += self.config.hybrid_weights.get("exact", 0.10) * exact_norm.get(cid, 0.0)
            base += self._signal_boost(chunk)
            results.append(
                {
                    "chunk_id": cid,
                    "chunk": chunk,
                    "hybrid_score": base,
                    "dense_score": dense_norm.get(cid, 0.0),
                    "sparse_score": sparse_norm.get(cid, 0.0),
                    "exact_hit": cid in exact_norm,
                }
            )
        results.sort(key=lambda item: item["hybrid_score"], reverse=True)
        return results

    def _exact_clause_hits(
        self, query: str, doc_filter: Optional[Iterable[str]]
    ) -> List[str]:
        clause_keys = set(self.CLAUSE_QUERY_RE.findall(query))
        std_matches = self.STANDARD_QUERY_RE.findall(query)
        doc_candidates = {" ".join(match).strip() for match in std_matches}
        results: List[str] = []
        for key in clause_keys:
            hits = self.clause_index.get_any(key)
            results.extend(hits)
            for doc in doc_candidates:
                composed_key = f"{doc}|{key}"
                results.extend(self.clause_index.get_any(composed_key))
        if doc_filter:
            allowed = set(doc_filter)
            results = [cid for cid in results if self._chunks.get(cid, {}).get("doc_id") in allowed]
        return sorted(dict.fromkeys(results))

    def _sparse_search(
        self,
        query: str,
        doc_filter: Optional[Iterable[str]],
        macro_filter: Optional[Iterable[str]],
    ) -> List[Tuple[str, float]]:
        tokens = tokenize(query)
        counts = Counter(tokens)
        scores: Dict[str, float] = {}
        for chunk_id, vector in self._sparse_vectors.items():
            if doc_filter and self._chunks.get(chunk_id, {}).get("doc_id") not in doc_filter:
                continue
            if macro_filter and chunk_id not in macro_filter:
                continue
            score = 0.0
            doc_len = sum(vector.values())
            for token, qf in counts.items():
                if token not in vector:
                    continue
                df = self._doc_frequency.get(token, 1)
                idf = math.log((len(self._sparse_vectors) - df + 0.5) / (df + 0.5) + 1)
                tf = vector[token]
                denom = tf + 1.5 * (0.25 + 0.75 * (doc_len / self._avg_doc_len))
                score += idf * (tf * (1.5 + 1) / denom)
            if score:
                scores[chunk_id] = score
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)

    def _dense_search(
        self,
        query: str,
        doc_filter: Optional[Iterable[str]],
        macro_filter: Optional[Iterable[str]],
    ) -> List[Tuple[str, float]]:
        query_vec = vectorize_tokens(tokenize(query))
        scores: Dict[str, float] = {}
        for chunk_id, vector in self._dense_vectors.items():
            if doc_filter and self._chunks.get(chunk_id, {}).get("doc_id") not in doc_filter:
                continue
            if macro_filter and chunk_id not in macro_filter:
                continue
            dot = sum(a * b for a, b in zip(query_vec, vector))
            scores[chunk_id] = dot
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)

    def _signal_boost(self, chunk: Dict[str, Any]) -> float:
        weights = self.scoring_config.get("weights", {})
        signals = chunk.get("signals", {})
        score = 0.0
        score += weights.get("modal_must_shall", 0.0) * signals.get("must_shall", 0)
        score += weights.get("numeric_units", 0.0) * (
            signals.get("numerics", 0) + signals.get("units", 0)
        )
        score += weights.get("modal_must_shall", 0.0) * signals.get("must_shall", 0)
        score += weights.get("heading_match", 0.0) * bool(
            (chunk.get("hier") or {}).get("heading")
        )
        score += weights.get("clause_id_match", 0.0) * bool(
            (chunk.get("hier") or {}).get("clause")
        )
        if signals.get("list"):
            score += weights.get("list_semantics", 0.0)
        if signals.get("refs"):
            score += weights.get("refs_present", 0.0)
        continuity = self._numbering_continuity(chunk)
        score += weights.get("numbering_continuity", 0.0) * continuity
        entropy_penalty = weights.get("entropy", -0.6) * signals.get("entropy", 0.0)
        score += entropy_penalty
        return score

    def _numbering_continuity(self, chunk: Dict[str, Any]) -> float:
        hier = chunk.get("hier") or {}
        clause_id = str(hier.get("clause") or "")
        doc_id = chunk.get("doc_id")
        if not clause_id or not doc_id:
            return 0.0
        parts = clause_id.split(".")
        if not parts:
            return 0.0
        try:
            last = int(re.sub(r"[^0-9]", "", parts[-1]) or 0)
        except ValueError:
            return 0.0
        prefix = parts[:-1]
        prev_clause = ".".join(prefix + [str(last - 1)]) if last > 0 else ""
        next_clause = ".".join(prefix + [str(last + 1)])
        clauses = self._doc_clause_numbers.get(str(doc_id), set())
        continuity = 0.0
        if prev_clause and prev_clause in clauses:
            continuity += 0.5
        if next_clause in clauses:
            continuity += 0.5
        return continuity

    def clause_candidates_from_query(self, query: str) -> List[str]:
        keys = list(self.CLAUSE_QUERY_RE.findall(query))
        for prefix, code in self.STANDARD_QUERY_RE.findall(query):
            keys.append(f"{prefix} {code}")
        return keys

    def get_chunk(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        return self._chunks.get(chunk_id)


def load_retriever(
    clause_index: ClauseIndex,
    *,
    config_path: str = "config/fluidrag.yaml",
) -> HybridRetriever:
    cfg = load_config(config_path)
    retrieval_cfg = cfg.get("retrieval", {})
    scoring_cfg = cfg.get("scoring", {})
    return HybridRetriever(clause_index, retrieval_cfg, scoring_cfg)


__all__ = ["HybridRetriever", "RetrievalConfig", "load_retriever"]
