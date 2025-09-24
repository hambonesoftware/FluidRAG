"""Evaluate header detection using weak gold."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..core.context import RAGContext
from ..core.router import pick_profile
from ..core.segmentation import detect_headers

TARGETS = {"recall": 0.90, "precision": 0.85, "f1": 0.87, "boundary_iou": 0.60}


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
    return gold


def _metrics(pred: List[int], gold: List[int]) -> Tuple[float, float, float]:
    pred_set = set(pred)
    gold_set = set(gold)
    tp = len(pred_set & gold_set)
    precision = tp / len(pred_set) if pred_set else 0.0
    recall = tp / len(gold_set) if gold_set else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return precision, recall, f1


def _spans(indices: List[int], total: int) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    if not indices:
        return spans
    sorted_idx = sorted(indices)
    for pos, start in enumerate(sorted_idx):
        end = total - 1
        if pos + 1 < len(sorted_idx):
            end = sorted_idx[pos + 1] - 1
        spans.append((start, max(start, end)))
    return spans


def _boundary_iou(pred_spans: List[Tuple[int, int]], gold_spans: List[Tuple[int, int]]) -> float:
    if not pred_spans or not gold_spans:
        return 0.0
    total = 0.0
    matches = 0
    for p_start, p_end in pred_spans:
        best = 0.0
        for g_start, g_end in gold_spans:
            inter_start = max(p_start, g_start)
            inter_end = min(p_end, g_end)
            if inter_end < inter_start:
                continue
            inter = inter_end - inter_start + 1
            union = (p_end - p_start + 1) + (g_end - g_start + 1) - inter
            if union <= 0:
                continue
            best = max(best, inter / union)
        if best > 0:
            total += best
            matches += 1
    if matches == 0:
        return 0.0
    return total / matches


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
    preds = [sec["start_idx"] for sec in sections]
    gold = _weak_gold(chunks)
    precision, recall, f1 = _metrics(preds, gold)
    pred_spans = _spans(preds, len(chunks))
    gold_spans = _spans(gold, len(chunks))
    iou = _boundary_iou(pred_spans, gold_spans)

    print(json.dumps({"precision": precision, "recall": recall, "f1": f1, "boundary_iou": iou}, indent=2))
    meets = (
        precision >= TARGETS["precision"]
        and recall >= TARGETS["recall"]
        and f1 >= TARGETS["f1"]
        and iou >= TARGETS["boundary_iou"]
    )
    status = "GREEN" if meets else "RED"
    print(f"Thresholds {TARGETS}, status: {status}")


if __name__ == "__main__":
    main()
