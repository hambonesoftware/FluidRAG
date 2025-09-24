"""High level orchestration for the RAG v2 pipeline."""
from __future__ import annotations

import logging
import re
from typing import Dict, Iterable, List, Optional

from backend.compat import to_legacy_llm_message

from .agents import FluidAgent, HEPAgent, StandardAgent
from .config import CFG
from .entropy import (
    entropy_changepoint_band,
    entropy_graph_band,
    entropy_linear_band,
)
from .fusion import fuse_scores, intersect_or_tightest_band
from .graph import GraphIndex
from .graph_summaries import build_graph_summaries
from .pack import pack_context
from .retrieval import Retriever
from .rerank import Reranker
from .sentence_window import attach_meso_parent, auto_merge_sentences, sentence_window_hits
from .types import Chunk, EvidenceBand, EvidenceScore, ExtractionJSON

log = logging.getLogger("FluidRAG.rag_v2")


def _order_chunks(chunks: Iterable[Chunk]) -> List[Chunk]:
    return sorted(
        chunks,
        key=lambda chunk: (
            chunk.doc_id,
            chunk.section_no or "",
            chunk.page_range[0],
            chunk.chunk_id,
        ),
    )


_GLOBAL_RE = re.compile(r"\b(?:compare|versus|vs\.?|difference|alignment)\b", re.I)
_STD_RE = re.compile(r"\b(?:NFPA|IEC|ISO|UL|OSHA|EN)\s?\d+[A-Z0-9]*\b")
_NUMERIC_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+)")


def _is_global_query(question: str) -> bool:
    std_matches = _STD_RE.findall(question or "")
    has_multi_std = len({match.upper() for match in std_matches}) >= 2
    return bool(_GLOBAL_RE.search(question or "") or has_multi_std)


def _detect_stage_conflicts(chunks: Iterable[Chunk]) -> List[Dict[str, object]]:
    records: Dict[tuple, Dict[str, List[str]]] = {}
    conflicts: List[Dict[str, object]] = []
    for chunk in chunks:
        numbers = _NUMERIC_RE.findall(chunk.text or "")
        if not numbers:
            continue
        key = (chunk.doc_id, chunk.section_no or chunk.section_title or "")
        bucket = records.setdefault(key, {})
        bucket.setdefault(chunk.stage_tag, []).extend(numbers)
    for key, stages in records.items():
        if len(stages) <= 1:
            continue
        normalized = {stage: sorted(set(values)) for stage, values in stages.items()}
        values = list(normalized.values())
        if len({tuple(v) for v in values}) <= 1:
            continue
        doc_id, section = key
        conflicts.append(
            {
                "doc_id": doc_id,
                "section": section,
                "values": normalized,
                "note": "specific-governs",
            }
        )
    return conflicts


def _seed_band(
    ordered: List[Chunk], fused: Dict[str, EvidenceScore], graph: GraphIndex
) -> EvidenceBand:
    if not ordered:
        raise ValueError("Cannot compute bands without chunks")
    top_chunk_id = max(fused.items(), key=lambda item: item[1].final)[0]
    seed_idx = next(
        (idx for idx, chunk in enumerate(ordered) if chunk.chunk_id == top_chunk_id),
        0,
    )
    band_a = entropy_linear_band(seed_idx, ordered)
    band_b = entropy_graph_band(ordered[seed_idx], ordered, graph)
    band_c = entropy_changepoint_band(seed_idx, ordered)
    return intersect_or_tightest_band([band_a, band_b, band_c], ordered)


def _default_extraction() -> ExtractionJSON:
    return ExtractionJSON()


def macro_pass(
    question: str,
    domain: str,
    edition_filters: Optional[Dict[str, str]] = None,
    *,
    retriever: Optional[Retriever] = None,
    reranker: Optional[Reranker] = None,
    graph: Optional[GraphIndex] = None,
) -> ExtractionJSON:
    if not CFG.rag_v2_enabled:
        log.info("[rag_v2] feature flag disabled; returning empty extraction")
        return _default_extraction()

    retriever = retriever or Retriever()
    reranker = reranker or Reranker()
    graph = graph or GraphIndex()

    pool = retriever.search(question, domain, edition_filters or {})
    pool = reranker.rerank(question, pool)

    graph_summaries: List[Dict[str, object]] = []
    if CFG.enable_graph_summaries and _is_global_query(question):
        try:
            summaries = build_graph_summaries(pool, top_k=CFG.topK_for_synthesis)
            graph_summaries = [summary.to_payload() for summary in summaries]
        except Exception:  # pragma: no cover - defensive
            log.exception("[rag_v2] failed to compute graph summaries")

    sentence_windows: List[Dict[str, object]] = []
    if CFG.enable_sentence_window:
        hits = []
        for chunk in pool[: CFG.k_sentence]:
            hits.extend(sentence_window_hits(chunk))
        merged = auto_merge_sentences(hits)
        sentence_windows = attach_meso_parent(merged, pool)

    standard_agent = StandardAgent()
    std_scores = standard_agent.score(question, pool)
    for chunk in pool:
        chunk.meta.setdefault("hybrid_score", std_scores.get(chunk.chunk_id, 0.0))
    fluid_agent = FluidAgent()
    flu_scores = fluid_agent.score(question, pool, graph)
    hep_agent = HEPAgent()
    hep_scores = hep_agent.score(question, pool)

    fused = fuse_scores(std_scores, flu_scores, hep_scores)
    ordered = _order_chunks(pool)
    if not ordered:
        result = _default_extraction()
        result.provenance = {
            "question": question,
            "domain": domain,
            "pool": 0,
            "rag_v2_enabled": True,
        }
        return result

    try:
        band = _seed_band(ordered, fused, graph)
    except Exception:  # pragma: no cover - defensive
        log.exception("[rag_v2] failed to compute entropy band; falling back to seed chunk")
        top_chunk = ordered[0]
        band = EvidenceBand(
            seed_chunk_id=top_chunk.chunk_id,
            start_idx=0,
            end_idx=0,
            confidence=0.5,
            entropy_trace_left=[],
            entropy_trace_right=[],
            method="fallback",
            band_chunk_ids=[top_chunk.chunk_id],
        )

    chunk_map = {chunk.chunk_id: chunk for chunk in ordered}
    context = pack_context(band, chunk_map, graph_summaries=graph_summaries)
    if sentence_windows:
        context.setdefault("SentenceWindows", sentence_windows)
    message = to_legacy_llm_message(context, question)

    extraction = _default_extraction()
    extraction.provenance = {
        "question": question,
        "domain": domain,
        "pool": len(pool),
        "fused_scores": {cid: score.final for cid, score in fused.items()},
        "band": {
            "seed": band.seed_chunk_id,
            "method": band.method,
            "size": len(band.band_chunk_ids),
        },
        "context": context,
        "llm_message": message,
    }
    if graph_summaries:
        extraction.provenance["graph_summaries"] = graph_summaries
    if sentence_windows:
        extraction.provenance["sentence_windows"] = sentence_windows
    conflicts = _detect_stage_conflicts(pool)
    if conflicts:
        extraction.provenance["conflicts"] = conflicts
    extraction.confidence = max(score.final for score in fused.values()) if fused else 0.0
    return extraction
