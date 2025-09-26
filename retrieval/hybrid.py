"""Hybrid retrieval pipeline that fuses lexical and embedding scores."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from ingest.microchunker import MicroChunk
from index import BM25Store, EmbeddingStore

RRF_K = 60


@dataclass
class _IndexSet:
    key: str
    prefix: str
    result_type: str
    bm25: Optional[BM25Store] = None
    embeddings: Optional[EmbeddingStore] = None
    docs: Mapping[str, Mapping[str, Any]] = None
    weight: float = 1.0

    def rank(self, query: str, k: int, rrf_fn) -> List[Tuple[str, float]]:
        rankings: List[List[str]] = []
        if self.embeddings:
            rankings.append([f"{self.prefix}{mid}" for mid, _ in self.embeddings.search(query, k)])
        if self.bm25:
            rankings.append([f"{self.prefix}{mid}" for mid, _ in self.bm25.search(query, k)])
        if not rankings:
            return []
        fused = rrf_fn(rankings, k)
        return [(doc_id, score * self.weight) for doc_id, score in fused]


class HybridRetriever:
    """Combine embedding, header, and table rankings using reciprocal rank fusion."""

    def __init__(
        self,
        *,
        embeddings: EmbeddingStore,
        bm25: BM25Store,
        micro_index: Mapping[str, MicroChunk],
        section_map: Optional[Mapping[str, Sequence[str]]] = None,
        header_embeddings: Optional[EmbeddingStore] = None,
        header_bm25: Optional[BM25Store] = None,
        header_docs: Optional[Sequence[Mapping[str, Any]]] = None,
        table_embeddings: Optional[EmbeddingStore] = None,
        table_bm25: Optional[BM25Store] = None,
        table_docs: Optional[Sequence[Mapping[str, Any]]] = None,
        span_map: Optional[Mapping[str, Mapping[str, Any]]] = None,
        log_path: Optional[Path] = None,
    ) -> None:
        self.micro_index = dict(micro_index)
        self.section_for_micro: Dict[str, Optional[str]] = {}
        for micro_id, micro in self.micro_index.items():
            self.section_for_micro[micro_id] = micro.get("section_id")
        if section_map:
            for section_id, micro_ids in section_map.items():
                for micro_id in micro_ids:
                    self.section_for_micro.setdefault(micro_id, section_id)

        self.span_map: Dict[str, Mapping[str, Any]] = {
            str(key): value for key, value in (span_map or {}).items()
        }

        header_mapping = {
            str(doc.get("micro_id")): dict(doc)
            for doc in (header_docs or [])
            if isinstance(doc, Mapping) and doc.get("micro_id")
        }
        table_mapping = {
            str(doc.get("micro_id")): dict(doc)
            for doc in (table_docs or [])
            if isinstance(doc, Mapping) and doc.get("micro_id")
        }

        self.index_sets: Dict[str, _IndexSet] = {
            "chunk": _IndexSet(
                key="chunk",
                prefix="chunk:",
                result_type="chunk",
                bm25=bm25,
                embeddings=embeddings,
                docs=self.micro_index,
                weight=1.0,
            )
        }
        if header_embeddings or header_bm25:
            self.index_sets["header"] = _IndexSet(
                key="header",
                prefix="header:",
                result_type="header",
                bm25=header_bm25,
                embeddings=header_embeddings,
                docs=header_mapping,
                weight=0.9,
            )
        if table_embeddings or table_bm25:
            self.index_sets["table"] = _IndexSet(
                key="table",
                prefix="table:",
                result_type="table",
                bm25=table_bm25,
                embeddings=table_embeddings,
                docs=table_mapping,
                weight=0.85,
            )

        self.log_path = Path(log_path) if log_path else None

    def _rrf(self, rankings: Sequence[Sequence[str]], k: int) -> List[Tuple[str, float]]:
        scores: MutableMapping[str, float] = defaultdict(float)
        for ranking in rankings:
            for rank, identifier in enumerate(ranking):
                scores[identifier] += 1.0 / (RRF_K + rank + 1)
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [(doc_id, score) for doc_id, score in ordered[:k]]

    def _span_boost(self, record: Mapping[str, Any], result_type: str) -> float:
        if not self.span_map:
            return 0.0
        candidate_ids: List[str] = []
        if result_type == "chunk":
            micro_id = record.get("micro_id") or record.get("chunk_id")
            if micro_id:
                candidate_ids.append(str(micro_id))
        elif result_type == "header":
            for micro_id in record.get("micro_ids", []):
                candidate_ids.append(str(micro_id))
        elif result_type == "table":
            for micro_id in record.get("parameter_supports", []):
                candidate_ids.append(str(micro_id))
        best = 0.0
        for micro_id in candidate_ids:
            entry = self.span_map.get(str(micro_id))
            if not entry:
                continue
            score = float(entry.get("score") or 0.0)
            if score > best:
                best = score
        if best <= 0.0:
            return 0.0
        return best * 0.05

    def _split_identifier(self, identifier: str) -> Tuple[str, str]:
        if ":" in identifier:
            return identifier.split(":", 1)
        return "chunk", identifier

    def search(self, query: str, k: int = 40) -> List[Dict[str, Any]]:
        dataset_rankings: List[List[str]] = []
        dataset_scores: Dict[str, float] = {}

        for dataset in self.index_sets.values():
            ranking = dataset.rank(query, k, self._rrf)
            if not ranking:
                continue
            dataset_rankings.append([identifier for identifier, _ in ranking])
            for identifier, score in ranking:
                dataset_scores[identifier] = max(dataset_scores.get(identifier, 0.0), score)

        if not dataset_rankings:
            return []

        fused = self._rrf(dataset_rankings, k)
        results: List[Dict[str, Any]] = []
        for identifier, base_score in fused:
            dataset_key, doc_id = self._split_identifier(identifier)
            dataset = self.index_sets.get(dataset_key)
            if not dataset:
                continue
            record = dataset.docs.get(doc_id)
            if not record and dataset.result_type == "chunk":
                record = self.micro_index.get(doc_id)
            if not record:
                continue
            combined_score = base_score + dataset_scores.get(identifier, 0.0)
            boost = self._span_boost(record, dataset.result_type)
            total = combined_score + boost
            results.append(
                {
                    "id": doc_id,
                    "type": dataset.result_type,
                    "score": round(total, 6),
                    "base_score": round(combined_score, 6),
                    "boost": round(boost, 6),
                    "record": record,
                }
            )

        results.sort(key=lambda item: item["score"], reverse=True)
        limited = results[:k]
        self._log(query, limited)
        return limited

    def _log(self, query: str, results: Sequence[Mapping[str, Any]]) -> None:
        if not self.log_path:
            return
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "query": query,
            "results": [
                {
                    "type": entry.get("type"),
                    "id": entry.get("id"),
                    "score": entry.get("score"),
                }
                for entry in results
            ],
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def rerank_by_section_density(
    micro_ids: Sequence[str],
    sections: Mapping[str, Mapping[str, Sequence[str]] | Sequence[str]] | Sequence[Mapping[str, object]],
    *,
    topk: int = 12,
    mmr_lambda: float = 0.3,
) -> List[str]:
    """Re-rank ``micro_ids`` such that dense sections rise to the top."""

    if not micro_ids:
        return []

    section_map: Dict[str, List[str]] = {}
    if isinstance(sections, Mapping):
        iterable: Iterable[tuple[str, Mapping[str, Sequence[str]] | Sequence[str]]] = sections.items()  # type: ignore[assignment]
    else:
        iterable = ((str(entry.get("section_id")), entry) for entry in sections if isinstance(entry, Mapping))

    for section_id, payload in iterable:
        if not section_id:
            continue
        if isinstance(payload, Mapping):
            micro_list = payload.get("micro_ids")
        else:
            micro_list = payload
        if not micro_list:
            continue
        section_map[str(section_id)] = [str(mid) for mid in micro_list]

    micro_to_section: Dict[str, str] = {}
    for section_id, micro_list in section_map.items():
        for micro_id in micro_list:
            micro_to_section[micro_id] = section_id

    density = Counter()
    for micro_id in micro_ids:
        section_id = micro_to_section.get(micro_id)
        if section_id:
            density[section_id] += 1
    total_density = sum(density.values()) or 1

    selected: List[str] = []
    seen: set[str] = set()
    if density:
        primary_section, _ = density.most_common(1)[0]
        primary_candidates = [mid for mid in micro_ids if micro_to_section.get(mid) == primary_section]
        if primary_candidates:
            first_primary = primary_candidates[0]
            selected.append(first_primary)
            seen.add(first_primary)
            for candidate in primary_candidates[1:]:
                if len(selected) >= topk:
                    break
                selected.append(candidate)
                seen.add(candidate)

    base_scores = {micro_id: 1.0 / (idx + 1) for idx, micro_id in enumerate(micro_ids)}
    section_weight = {
        section_id: count / total_density
        for section_id, count in density.items()
    }

    while len(selected) < min(topk, len(micro_ids)):
        best_id = None
        best_score = float("-inf")
        for micro_id in micro_ids:
            if micro_id in seen:
                continue
            base = base_scores[micro_id]
            section_id = micro_to_section.get(micro_id)
            dens = section_weight.get(section_id, 0.0)
            novelty = 1.0
            if selected and section_id:
                overlap = sum(1 for chosen in selected if micro_to_section.get(chosen) == section_id)
                novelty = 1.0 / (1 + overlap)
            score = (1.0 - mmr_lambda) * base * novelty + mmr_lambda * dens
            if score > best_score:
                best_id = micro_id
                best_score = score
        if best_id is None:
            break
        selected.append(best_id)
        seen.add(best_id)
    return selected


__all__ = ["HybridRetriever", "rerank_by_section_density"]
