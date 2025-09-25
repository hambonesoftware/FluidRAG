"""Evaluate header detection using weak gold."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..core.context import RAGContext
from ..core.router import pick_profile
from ..core.segmentation import detect_headers

TARGETS = {"recall": 0.90, "precision": 0.85, "f1": 0.87}


def _load_profiles(path: Path) -> Dict[str, Any]:
    import yaml

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _hash_config(path: Path) -> str:
    import hashlib

    return hashlib.sha1(path.read_bytes()).hexdigest()


def _weak_gold(chunks: List[Dict[str, Any]]) -> List[int]:
    import re

    gold = []
    for idx, chunk in enumerate(chunks):
        text = chunk.get("text", "")
        if re.match(r"^(\d+|Appendix|Table|Figure)", text):
            gold.append(idx)
            continue
        meta = chunk.get("meta", {})
        if meta.get("is_heading"):
            gold.append(idx)
    return gold


def _spans_from_boundaries(boundaries: List[int], total: int) -> List[Tuple[int, int]]:
    spans = []
    for idx, start in enumerate(sorted(boundaries)):
        end = total - 1
        if idx + 1 < len(boundaries):
            end = max(start, boundaries[idx + 1] - 1)
        spans.append((start, end))
    return spans


def _iou(span_a: Tuple[int, int], span_b: Tuple[int, int]) -> float:
    a_start, a_end = span_a
    b_start, b_end = span_b
    inter_start = max(a_start, b_start)
    inter_end = min(a_end, b_end)
    if inter_end < inter_start:
        return 0.0
    inter = inter_end - inter_start + 1
    union = (a_end - a_start + 1) + (b_end - b_start + 1) - inter
    return inter / union if union else 0.0


def _metrics(pred_spans: List[Tuple[int, int]], gold_spans: List[Tuple[int, int]], threshold: float = 0.6):
    matched_gold = set()
    tp = 0
    iou_scores: List[float] = []
    for span in pred_spans:
        best_iou = 0.0
        best_idx = None
        for idx, gold_span in enumerate(gold_spans):
            if idx in matched_gold:
                continue
            iou_val = _iou(span, gold_span)
            if iou_val > best_iou:
                best_iou = iou_val
                best_idx = idx
        if best_iou >= threshold and best_idx is not None:
            tp += 1
            matched_gold.add(best_idx)
            iou_scores.append(best_iou)
    precision = tp / len(pred_spans) if pred_spans else 0.0
    recall = tp / len(gold_spans) if gold_spans else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    avg_iou = sum(iou_scores) / len(iou_scores) if iou_scores else 0.0
    return precision, recall, f1, avg_iou


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", required=True)
    parser.add_argument("--pass", dest="ppass", required=True)
    parser.add_argument("--profiles", default="ragx/config/profiles.yaml")
    args = parser.parse_args()

    doc = json.loads(Path(args.doc).read_text())
    chunks = doc.get("chunks", [])
    profiles = _load_profiles(Path(args.profiles))
    version = _hash_config(Path(args.profiles))
    context = RAGContext(doc.get("doc_id", "doc"), args.ppass, "HEADER", args.ppass, version)
    profile = pick_profile(args.ppass, "HEADER", profiles)
    sections = detect_headers(chunks, None, None, profile, context)
    preds = _spans_from_boundaries([sec["start_idx"] for sec in sections], len(chunks))
    gold = _spans_from_boundaries(_weak_gold(chunks), len(chunks))
    precision, recall, f1, avg_iou = _metrics(preds, gold)

    print(json.dumps({"precision": precision, "recall": recall, "f1": f1, "avg_iou": avg_iou}, indent=2))
    meets = precision >= TARGETS["precision"] and recall >= TARGETS["recall"] and f1 >= TARGETS["f1"]
    status = "GREEN" if meets else "RED"
    print(f"Thresholds {TARGETS} | Avg IoU≥0.6 matched: {avg_iou:.2f} | status: {status}")


if __name__ == "__main__":
    main()
