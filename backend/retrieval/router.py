"""Hierarchical retrieval router for standards queries."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from fluidrag.config import load_config

from ..indexes.clause_index import ClauseIndex
from .rerankers import select_reranker
from .retrieval import HybridRetriever, load_retriever
from .utils import tokenize


@dataclass
class RouteResult:
    final_chunks: List[Dict[str, Any]]
    candidates: List[Dict[str, Any]]
    doc_candidates: List[Tuple[str, float]]
    macro_candidates: List[Tuple[str, float]]


def _score_documents(
    query_tokens: Sequence[str],
    macros: Sequence[Dict[str, Any]],
    discipline: Optional[str],
    routing_cfg: Dict[str, Any],
) -> List[Tuple[str, float]]:
    scores: Dict[str, float] = defaultdict(float)
    discipline_keywords = routing_cfg.get("discipline_keywords", {})
    discipline_terms = [term.lower() for term in discipline_keywords.get(discipline, [])]
    for macro in macros:
        doc_id = macro.get("doc_id")
        text_tokens = set(tokenize(str(doc_id) + " " + macro.get("hier_path", "")))
        overlap = len(set(query_tokens) & text_tokens)
        if overlap:
            scores[doc_id] += overlap
        for term in discipline_terms:
            if term in doc_id.lower() or term in macro.get("hier_path", "").lower():
                scores[doc_id] += 1.0
    if not scores:
        for macro in macros:
            scores[macro.get("doc_id")] += 0.1
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)


def _score_macros(
    query_tokens: Sequence[str],
    macros: Sequence[Dict[str, Any]],
    doc_ids: Iterable[str],
) -> List[Tuple[str, float]]:
    scores: List[Tuple[str, float]] = []
    doc_set = set(doc_ids)
    for macro in macros:
        if macro.get("doc_id") not in doc_set:
            continue
        tokens = set(tokenize(macro.get("text", "")))
        overlap = len(tokens & set(query_tokens))
        score = overlap / max(len(tokens), 1)
        scores.append((macro["macro_id"], score))
    scores.sort(key=lambda item: item[1], reverse=True)
    return scores


def route_query(
    query: str,
    discipline: Optional[str],
    retriever: HybridRetriever,
    clause_index: ClauseIndex,
    macro_chunks: Sequence[Dict[str, Any]],
    *,
    config_path: str = "config/fluidrag.yaml",
) -> RouteResult:
    cfg = load_config(config_path)
    retrieval_cfg = cfg.get("retrieval", {})
    routing_cfg = cfg.get("routing", {})
    reranker = select_reranker(retrieval_cfg.get("reranker"))

    clause_keys = retriever.clause_candidates_from_query(query)
    direct_hits: List[Dict[str, Any]] = []
    seen_hits: set[str] = set()
    for key in clause_keys:
        for chunk_id in clause_index.get_any(key):
            if chunk_id in seen_hits:
                continue
            chunk = retriever.get_chunk(chunk_id)
            if chunk:
                direct_hits.append({"chunk_id": chunk_id, "chunk": chunk, "hybrid_score": 1.0})
                seen_hits.add(chunk_id)
    if direct_hits:
        reranked = reranker.rerank(query, direct_hits)
        final_k = retrieval_cfg.get("k_final", 1)
        allow_multi = retrieval_cfg.get("allow_multi_final", False)
        limit = final_k if allow_multi else 1
        return RouteResult(reranked[:limit], reranked, [], [])

    query_tokens = tokenize(query)
    doc_scores = _score_documents(query_tokens, macro_chunks, discipline, routing_cfg)
    top_docs = [doc for doc, _ in doc_scores[:2]]

    macro_scores = _score_macros(query_tokens, macro_chunks, top_docs)
    top_macro_ids = [macro_id for macro_id, _ in macro_scores[:2]]
    macro_micro_ids: List[str] = []
    for macro in macro_chunks:
        if macro.get("macro_id") in top_macro_ids:
            macro_micro_ids.extend(macro.get("micro_children", []))
    macro_micro_ids = list({str(mid) for mid in macro_micro_ids})

    candidates = retriever.retrieve(
        query,
        discipline=discipline,
        doc_filter=top_docs,
        macro_filter=macro_micro_ids,
    )
    reranked = reranker.rerank(query, candidates)
    final_k = retrieval_cfg.get("k_final", 1)
    allow_multi = retrieval_cfg.get("allow_multi_final", False)
    limit = final_k if allow_multi else 1
    return RouteResult(
        reranked[:limit],
        reranked,
        doc_scores[:2],
        macro_scores[:2],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Route a standards query")
    parser.add_argument("--query", required=True)
    parser.add_argument("--discipline", default=None)
    parser.add_argument("--config", default="config/fluidrag.yaml")
    parser.add_argument("--macro", type=Path, help="Path to macro chunk JSON", required=True)
    parser.add_argument("--micro", type=Path, help="Path to micro chunk JSON", required=True)
    args = parser.parse_args()

    clause_index = ClauseIndex()
    retriever = load_retriever(clause_index, config_path=args.config)
    micro_chunks = json.loads(args.micro.read_text(encoding="utf-8"))
    macro_chunks = json.loads(args.macro.read_text(encoding="utf-8"))
    macro_map = {macro["macro_id"]: macro.get("micro_children", []) for macro in macro_chunks}
    retriever.index(micro_chunks, macro_map=macro_map)

    result = route_query(
        args.query,
        args.discipline,
        retriever,
        clause_index,
        macro_chunks,
        config_path=args.config,
    )
    print(json.dumps({
        "final": [item["chunk_id"] for item in result.final_chunks],
        "candidates": [item["chunk_id"] for item in result.candidates],
        "doc_candidates": result.doc_candidates,
        "macro_candidates": result.macro_candidates,
    }, indent=2))


if __name__ == "__main__":
    main()
