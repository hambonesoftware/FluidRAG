"""Hybrid retrieval pipeline that fuses lexical and embedding scores."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

from ingest.microchunker import MicroChunk
from index import BM25Store, EmbeddingStore

RRF_K = 60


class HybridRetriever:
    """Combine embedding and lexical rankings using reciprocal rank fusion."""

    def __init__(
        self,
        *,
        embeddings: EmbeddingStore,
        bm25: BM25Store,
        micro_index: Mapping[str, MicroChunk],
        section_map: Optional[Mapping[str, Sequence[str]]] = None,
        log_path: Optional[Path] = None,
    ) -> None:
        self.embeddings = embeddings
        self.bm25 = bm25
        self.micro_index = dict(micro_index)
        self.section_for_micro: Dict[str, Optional[str]] = {}
        for micro_id, micro in self.micro_index.items():
            self.section_for_micro[micro_id] = micro.get("section_id")
        if section_map:
            for section_id, micro_ids in section_map.items():
                for micro_id in micro_ids:
                    self.section_for_micro.setdefault(micro_id, section_id)
        self.log_path = Path(log_path) if log_path else None

    def _rrf(self, rankings: Sequence[Sequence[str]], k: int) -> List[str]:
        scores: MutableMapping[str, float] = defaultdict(float)
        for ranking in rankings:
            for rank, micro_id in enumerate(ranking):
                scores[micro_id] += 1.0 / (RRF_K + rank + 1)
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return [mid for mid, _ in ordered[:k]]

    def search(self, query: str, k: int = 40) -> List[str]:
        embedding_hits = [mid for mid, _ in self.embeddings.search(query, k)]
        bm25_hits = [mid for mid, _ in self.bm25.search(query, k)]
        rankings = [hits for hits in (embedding_hits, bm25_hits) if hits]
        if not rankings:
            return []
        fused = self._rrf(rankings, k)
        self._log(query, fused[:k])
        return fused[:k]

    def _log(self, query: str, micro_ids: Sequence[str]) -> None:
        if not self.log_path:
            return
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "query": query,
            "micro_ids": list(micro_ids),
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
