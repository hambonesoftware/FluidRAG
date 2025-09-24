from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from fluidrag.src.chunking.standard import Chunk

CLAUSE_REGEX = re.compile(r"\b\d+(?:\.\d+){1,}\b")
STANDARD_REGEX = re.compile(r"\b(?:ISO|IEC|NFPA|UL|IEEE|EN)\s?[0-9A-Za-z:\-]+\b", re.IGNORECASE)
NORMATIVE_TOKENS = {"shall", "must", "required"}


@dataclass
class RetrievalHit:
    chunk_id: str
    score: float
    text: str
    chunk: Chunk
    stage: str


class RetrievalStack:
    def __init__(self, chunks: Sequence[Chunk], config: dict) -> None:
        self.chunks = list(chunks)
        self.config = config
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.doc_matrix = self.vectorizer.fit_transform(chunk.text for chunk in self.chunks)

    def _clause_boost(self, query: str, chunk: Chunk) -> float:
        clause_matches = CLAUSE_REGEX.findall(query)
        if not clause_matches:
            return 0.0
        chunk_text = chunk.text
        for clause in clause_matches:
            if clause in chunk_text:
                return self.config["retrieval"]["features"].get("clause_regex_boost", 0.0)
        return 0.0

    def _normative_boost(self, chunk: Chunk) -> float:
        tokens = re.findall(r"[A-Za-z]+", chunk.text.lower())
        norm_count = sum(1 for token in tokens if token in NORMATIVE_TOKENS)
        if not tokens:
            return 0.0
        boost_value = self.config["retrieval"]["features"]["normative_boost"]["value"]
        return boost_value * (norm_count / len(tokens))

    def _numeric_boost(self, chunk: Chunk) -> float:
        numerics = re.findall(r"\d", chunk.text)
        if not numerics:
            return 0.0
        return self.config["retrieval"]["features"].get("unit_numeric_boost", 0.0)

    def _exact_clause_match(self, query: str) -> List[RetrievalHit]:
        clause_matches = CLAUSE_REGEX.findall(query)
        if not clause_matches:
            return []
        hits: list[RetrievalHit] = []
        for chunk in self.chunks:
            for clause in clause_matches:
                if clause in chunk.text:
                    hits.append(RetrievalHit(chunk_id=chunk.chunk_id, score=1.0, text=chunk.text, chunk=chunk, stage="clause"))
                    break
        return hits

    def _sparse_search(self, query: str, topk: int) -> List[RetrievalHit]:
        query_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self.doc_matrix)[0]
        ranked = sorted(zip(self.chunks, scores), key=lambda x: x[1], reverse=True)[:topk]
        return [RetrievalHit(chunk_id=chunk.chunk_id, score=float(score), text=chunk.text, chunk=chunk, stage="sparse") for chunk, score in ranked if score > 0]

    def _hyde_queries(self, query: str, n: int) -> List[str]:
        return [query] + [f"Scenario {i}: {query}" for i in range(1, n + 1)]

    def _dense_search(self, query: str, topk: int, hyde_enabled: bool, hyde_n: int) -> List[RetrievalHit]:
        queries = [query]
        if hyde_enabled:
            queries = self._hyde_queries(query, hyde_n)
        query_vecs = self.vectorizer.transform(queries)
        scores = cosine_similarity(query_vecs, self.doc_matrix)
        merged_scores = scores.max(axis=0)
        ranked = sorted(zip(self.chunks, merged_scores), key=lambda x: x[1], reverse=True)[:topk]
        return [RetrievalHit(chunk_id=chunk.chunk_id, score=float(score), text=chunk.text, chunk=chunk, stage="dense") for chunk, score in ranked if score > 0]

    def _colbert_rerank(self, hits: List[RetrievalHit], topk: int) -> List[RetrievalHit]:
        reranked = sorted(hits, key=lambda hit: len(hit.text.split()), reverse=True)
        return [RetrievalHit(chunk_id=hit.chunk_id, score=hit.score + 0.05, text=hit.text, chunk=hit.chunk, stage="colbert") for hit in reranked[:topk]]

    def search(self, query: str, view: str = "standard", topk: int = 10) -> List[RetrievalHit]:
        clause_hits = self._exact_clause_match(query)
        sparse_hits = self._sparse_search(query, self.config["retrieval"]["sparse"]["topk"])
        dense_config = self.config["retrieval"]["dense"]
        dense_hits = self._dense_search(query, dense_config["topk"], dense_config["hyde"]["enabled"], dense_config["hyde"].get("n", 2))

        candidate_map: Dict[str, RetrievalHit] = {}
        for hit in clause_hits + sparse_hits + dense_hits:
            candidate_map.setdefault(hit.chunk_id, hit)

        hits = list(candidate_map.values())
        for hit in hits:
            boosts = self._normative_boost(hit.chunk) + self._numeric_boost(hit.chunk) + self._clause_boost(query, hit.chunk)
            hit.score += boosts

        hits.sort(key=lambda h: h.score, reverse=True)
        cascade = self.config["retrieval"]["cascade"]
        if cascade.get("colbert", {}).get("enabled", False):
            hits = self._colbert_rerank(hits[: cascade["merge_topk"]], cascade["colbert"]["re_rank_topk"])

        filtered: List[RetrievalHit] = []
        if view == "standard":
            filtered = hits
        elif view == "fluid":
            filtered = [hit for hit in hits if hit.chunk.scores.get("fluid_above_threshold")]
        elif view == "hep":
            filtered = [hit for hit in hits if hit.chunk.scores.get("hep_above_threshold")]
        else:
            filtered = hits

        return filtered[:topk]


def search_standard(query: str, chunks: Sequence[Chunk], config: dict, view: str = "standard", topk: int = 10) -> List[RetrievalHit]:
    stack = RetrievalStack(chunks, config)
    return stack.search(query, view=view, topk=topk)


__all__ = ["search_standard", "RetrievalStack", "RetrievalHit"]
