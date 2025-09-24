"""Adaptive segmentation utilities."""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

from .context import RAGContext
from .signals import (
    cluster_switch,
    delta_entropy,
    embedding_drift,
    layout_score,
    numbering_score,
    regex_prior,
    smoothed_entropy,
)
from .utils import build_anchor


_DEF_STD_EPS = 1e-6


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    tokens = re.findall(r"\w+", text.lower())
    if not tokens:
        return 0.0
    total = len(tokens)
    freq: Dict[str, int] = {}
    for tok in tokens:
        freq[tok] = freq.get(tok, 0) + 1
    entropy = 0.0
    for count in freq.values():
        p = count / total
        entropy -= p * math.log(p + 1e-12, 2)
    return entropy


def _zscore_threshold(scores: List[float], lam: float) -> float:
    if not scores:
        return float("inf")
    mean = sum(scores) / len(scores)
    var = sum((s - mean) ** 2 for s in scores) / max(len(scores) - 1, 1)
    std = math.sqrt(var + _DEF_STD_EPS)
    return mean + lam * std


def detect_headers(chunks, embeddings, clusters, profile, context: RAGContext):
    """
    Return meso sections with signal traces and break decisions.
    """

    seg_cfg = profile.get("segmentation", {})
    weights = seg_cfg.get("weights", {})
    heading_patterns = seg_cfg.get("heading_regex_boosts", [])
    token_boosts = set(tok.lower() for tok in seg_cfg.get("token_boosts", []))
    min_gap = seg_cfg.get("min_gap", 1)
    threshold_cfg = seg_cfg.get("threshold", {"mode": "zscore", "lambda": 1.0})

    entropies = [_shannon_entropy(chunk.get("text", "")) for chunk in chunks]
    smoothed = smoothed_entropy(entropies, window=2)
    delta = delta_entropy(smoothed)

    signal_traces: Dict[str, List[float]] = {
        "delta_entropy": delta,
        "embedding_drift": [],
        "cluster_switch": [],
        "regex": [],
        "number": [],
        "layout": [],
    }

    scores: List[float] = []
    prev_embedding = None
    prev_cluster = None
    for idx, chunk in enumerate(chunks):
        text = chunk.get("text", "")
        meta = chunk.get("meta", {})
        cur_embedding = None
        if embeddings and idx < len(embeddings):
            cur_embedding = embeddings[idx]
        drift = embedding_drift(prev_embedding, cur_embedding)
        prev_embedding = cur_embedding
        signal_traces["embedding_drift"].append(drift)

        cluster_val = None
        if clusters and idx < len(clusters):
            cluster_val = clusters[idx]
        cswitch = cluster_switch(prev_cluster, cluster_val)
        prev_cluster = cluster_val
        signal_traces["cluster_switch"].append(cswitch)

        regex_score = regex_prior(text, heading_patterns)
        if token_boosts:
            token_hits = sum(1 for token in token_boosts if token in text.lower())
            regex_score += 0.25 * token_hits
        signal_traces["regex"].append(regex_score)

        num_score = numbering_score(text)
        signal_traces["number"].append(num_score)

        lay_score = layout_score(meta)
        signal_traces["layout"].append(lay_score)

        score = (
            weights.get("wH", 0.0) * (delta[idx] if idx < len(delta) else 0.0)
            + weights.get("wD", 0.0) * drift
            + weights.get("wC", 0.0) * cswitch
            + weights.get("wR", 0.0) * regex_score
            + weights.get("wN", 0.0) * num_score
            + weights.get("wL", 0.0) * lay_score
        )
        scores.append(score)

    if threshold_cfg.get("mode") == "zscore":
        threshold = _zscore_threshold(scores, threshold_cfg.get("lambda", 1.0))
    else:
        threshold = threshold_cfg.get("value", 0.0)

    def _add_section(idx: int, score: float, counter: int) -> Dict[str, Any]:
        chunk = chunks[idx]
        text = chunk.get("text", "").strip()
        meta = chunk.get("meta", {})
        name = text.split("\n", 1)[0][:120]
        section_id = meta.get("section_id") or f"sec{counter:03d}"
        page = meta.get("page", 1)
        anchors = [build_anchor(meta.get("number"), name)]
        return {
            "section_id": section_id,
            "section_name": name,
            "page_start": page,
            "page_end": page,
            "start_idx": idx,
            "end_idx": idx,
            "anchors": anchors,
            "signals": signal_traces,
            "break_score": score,
        }

    sections: List[Dict[str, Any]] = []
    last_break = -min_gap
    section_counter = 0
    for idx, score in enumerate(scores):
        if idx == 0:
            is_peak = True
        else:
            left = scores[idx - 1]
            right = scores[idx + 1] if idx + 1 < len(scores) else scores[idx]
            is_peak = score >= left and score >= right
        if not is_peak:
            continue
        if score < threshold:
            continue
        if idx - last_break < min_gap:
            continue
        last_break = idx
        section_counter += 1
        sections.append(_add_section(idx, score, section_counter))

    if not sections:
        peaks = sorted(((score, idx) for idx, score in enumerate(scores)), reverse=True)
        chosen = []
        for score, idx in peaks:
            if score <= 0:
                break
            if any(abs(idx - other) < min_gap for other in chosen):
                continue
            section_counter += 1
            sections.append(_add_section(idx, score, section_counter))
            chosen.append(idx)
        sections.sort(key=lambda s: s["start_idx"]) 

    # extend section end indices to next section - 1
    for sec_idx, section in enumerate(sections):
        end_idx = len(chunks) - 1
        page_end = section["page_end"]
        if sec_idx + 1 < len(sections):
            end_idx = sections[sec_idx + 1]["start_idx"] - 1
            next_page = sections[sec_idx + 1]["page_start"]
            page_end = max(page_end, next_page)
        section["end_idx"] = max(section["start_idx"], end_idx)
        section["page_end"] = page_end

    return sections
