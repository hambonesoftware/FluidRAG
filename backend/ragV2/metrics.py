"""Lightweight evaluation helpers for header detection and retrieval."""
from __future__ import annotations

import math
from typing import Dict, Iterable, Sequence

from .headers import HEADER_REGEX


def header_detection_metrics(chunks: Sequence[Dict[str, object]]) -> Dict[str, float]:
    """Compute precision/recall/F1 against regex-numbering pseudo labels."""

    gold_indices = {
        idx
        for idx, chunk in enumerate(chunks)
        if HEADER_REGEX.match(str(chunk.get("text", "")).splitlines()[0] if chunk.get("text") else "")
        or chunk.get("section_number")
    }
    predicted_indices = {idx for idx, chunk in enumerate(chunks) if chunk.get("header_candidate")}
    true_positive = len(gold_indices & predicted_indices)
    precision = true_positive / max(len(predicted_indices), 1)
    recall = true_positive / max(len(gold_indices), 1)
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "gold": len(gold_indices),
        "predicted": len(predicted_indices),
    }


def _dcg(relevances: Sequence[int]) -> float:
    value = 0.0
    for idx, rel in enumerate(relevances, start=1):
        value += (2**rel - 1) / math.log2(idx + 1)
    return value


def retrieval_metrics(
    ranked_ids: Sequence[str],
    relevant_ids: Iterable[str],
    k_values: Sequence[int] = (5, 10),
) -> Dict[str, float]:
    relevant = set(relevant_ids)
    gains = [1 if cid in relevant else 0 for cid in ranked_ids]
    metrics: Dict[str, float] = {}
    for k in k_values:
        window = gains[:k]
        recall = sum(window) / max(len(relevant), 1)
        ideal = sorted(gains, reverse=True)[:k]
        ndcg = 0.0
        if any(window):
            ndcg = _dcg(window) / max(_dcg(ideal), 1e-9)
        metrics[f"Recall@{k}"] = recall
        metrics[f"nDCG@{k}"] = ndcg
    return metrics

