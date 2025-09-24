"""Sentence-level retrieval helpers with auto-merge of adjacent sentences."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

from .config import CFG
from .types import Chunk


_sentence_re = re.compile(r"(?<=[.!?])\s+")


@dataclass
class SentenceHit:
    chunk_id: str
    sentence: str
    score: float
    offset: int
    resolution: str


def _split_sentences(text: str) -> List[str]:
    if not text:
        return []
    sentences = [sentence.strip() for sentence in _sentence_re.split(text) if sentence.strip()]
    if not sentences:
        sentences = [text.strip()]
    return sentences


def sentence_window_hits(chunk: Chunk, signal_key: str = "hybrid_score") -> List[SentenceHit]:
    meta = chunk.meta or {}
    base_score = float(meta.get(signal_key, meta.get("retrieval_rank", 0)))
    sentences = _split_sentences(chunk.text)
    hits: List[SentenceHit] = []
    for idx, sentence in enumerate(sentences):
        local_score = base_score
        if len(sentence) < 20:
            local_score *= 0.8
        hits.append(
            SentenceHit(
                chunk_id=chunk.chunk_id,
                sentence=sentence,
                score=local_score,
                offset=idx,
                resolution=chunk.resolution,
            )
        )
    return hits


def auto_merge_sentences(hits: Sequence[SentenceHit]) -> List[Dict[str, object]]:
    if not hits:
        return []
    grouped: Dict[str, List[SentenceHit]] = {}
    for hit in hits:
        grouped.setdefault(hit.chunk_id, []).append(hit)
    merged_payloads: List[Dict[str, object]] = []
    for chunk_id, chunk_hits in grouped.items():
        chunk_hits.sort(key=lambda item: item.offset)
        window: List[SentenceHit] = []
        for hit in chunk_hits:
            if not window:
                window = [hit]
                continue
            prev = window[-1]
            if hit.offset - prev.offset <= CFG.sentence_neighbor_radius:
                window.append(hit)
                continue
            merged_payloads.append(_emit_window(window))
            window = [hit]
        if window:
            merged_payloads.append(_emit_window(window))
    return merged_payloads


def _emit_window(window: Sequence[SentenceHit]) -> Dict[str, object]:
    if not window:
        return {}
    window = list(window)
    combined = " ".join(hit.sentence for hit in window)
    tokens = len(combined.split())
    score = max(hit.score for hit in window)
    payload = {
        "chunk_id": window[0].chunk_id,
        "sentence_start": window[0].offset,
        "sentence_end": window[-1].offset,
        "text": combined,
        "score": score,
        "token_len": tokens,
        "resolution": window[0].resolution,
    }
    payload["within_budget"] = tokens <= CFG.sentence_max_tokens
    return payload


def attach_meso_parent(
    merged: Iterable[Dict[str, object]], pool: Sequence[Chunk]
) -> List[Dict[str, object]]:
    enriched: List[Dict[str, object]] = []
    chunk_map = {chunk.chunk_id: chunk for chunk in pool}
    for window in merged:
        chunk_id = str(window.get("chunk_id"))
        source = chunk_map.get(chunk_id)
        meso_parent = None
        if source is not None:
            parent_id = source.meta.get("meso_parent_id") if source.meta else None
            if parent_id:
                meso_parent = chunk_map.get(parent_id)
        payload = dict(window)
        if meso_parent is not None:
            payload["meso_parent"] = {
                "chunk_id": meso_parent.chunk_id,
                "text": meso_parent.text,
                "stage_tag": meso_parent.stage_tag,
            }
        enriched.append(payload)
    return enriched

