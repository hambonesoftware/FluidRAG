"""Quality assurance metrics for clause extraction."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Sequence


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        curr = [i]
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def _is_atomic(text: str) -> bool:
    if not text:
        return True
    normalized = " ".join(text.lower().split())
    if normalized.count(" shall ") > 1 and ";" in normalized:
        return False
    if " shall " in normalized and " and " in normalized:
        return False
    return True


def atomicity_score(chunks: Sequence[Dict[str, object]]) -> float:
    total = len(chunks)
    if total == 0:
        return 1.0
    singles = sum(1 for chunk in chunks if _is_atomic(str(chunk.get("text", ""))))
    return singles / total


def verbatim_fidelity(
    predictions: Sequence[Dict[str, object]],
    source_lookup: Dict[str, str],
) -> float:
    perfect = 0
    total = 0
    for item in predictions:
        source = item.get("source") or {}
        if isinstance(source, dict):
            key = source.get("chunk_id") or source.get("id")
        else:
            key = item.get("source_id")
        if not key:
            continue
        exact = str(item.get("exact_text", ""))
        source_text = source_lookup.get(str(key))
        if source_text is None:
            continue
        total += 1
        if _levenshtein(exact, source_text) == 0:
            perfect += 1
    if total == 0:
        return 1.0
    return perfect / total


def rerank_uplift(
    baseline_top1: Sequence[str],
    reranked_top1: Sequence[str],
    gold_top1: Sequence[str],
) -> Dict[str, float]:
    count = min(len(baseline_top1), len(reranked_top1), len(gold_top1))
    if count == 0:
        return {"baseline_accuracy": 0.0, "reranked_accuracy": 0.0, "uplift": 0.0}
    base_correct = sum(1 for b, g in zip(baseline_top1[:count], gold_top1[:count]) if b == g)
    rerank_correct = sum(1 for r, g in zip(reranked_top1[:count], gold_top1[:count]) if r == g)
    return {
        "baseline_accuracy": base_correct / count,
        "reranked_accuracy": rerank_correct / count,
        "uplift": (rerank_correct - base_correct) / count,
    }


def unit_number_capture(
    gold: Sequence[Dict[str, Sequence[str]]],
    pred: Sequence[Dict[str, Sequence[str]]],
) -> Dict[str, float]:
    def flatten(records: Sequence[Dict[str, Sequence[str]]], field: str) -> List[str]:
        values: List[str] = []
        for record in records:
            values.extend(str(value) for value in record.get(field, []) or [])
        return values

    gold_numbers = set(flatten(gold, "numbers"))
    gold_units = set(flatten(gold, "units"))
    pred_numbers = set(flatten(pred, "numbers"))
    pred_units = set(flatten(pred, "units"))

    num_tp = len(gold_numbers & pred_numbers)
    unit_tp = len(gold_units & pred_units)

    number_precision = num_tp / len(pred_numbers) if pred_numbers else 1.0
    number_recall = num_tp / len(gold_numbers) if gold_numbers else 1.0
    unit_precision = unit_tp / len(pred_units) if pred_units else 1.0
    unit_recall = unit_tp / len(gold_units) if gold_units else 1.0

    return {
        "number_precision": number_precision,
        "number_recall": number_recall,
        "unit_precision": unit_precision,
        "unit_recall": unit_recall,
    }


__all__ = [
    "atomicity_score",
    "verbatim_fidelity",
    "rerank_uplift",
    "unit_number_capture",
]
