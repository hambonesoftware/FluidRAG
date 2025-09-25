"""Command line interface to evaluate QA metrics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from backend.qa.metrics import (
    atomicity_score,
    rerank_uplift,
    unit_number_capture,
    verbatim_fidelity,
)


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            rows.append(json.loads(stripped))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate FluidRAG QA metrics")
    parser.add_argument("--gold", type=Path, required=True, help="Path to gold JSONL")
    parser.add_argument("--pred", type=Path, required=True, help="Path to predictions JSONL")
    parser.add_argument("--report", type=Path, required=True, help="Report output path")
    args = parser.parse_args()

    gold_rows = _load_jsonl(args.gold)
    pred_rows = _load_jsonl(args.pred)

    chunk_lookup = {row.get("chunk_id"): row.get("text", "") for row in gold_rows if row.get("chunk_id")}

    report: Dict[str, Any] = {}
    report["atomicity"] = atomicity_score(gold_rows)
    report["verbatim_fidelity"] = verbatim_fidelity(pred_rows, chunk_lookup)

    baseline = [row.get("baseline_top1") for row in pred_rows if row.get("baseline_top1")]
    reranked = [row.get("reranked_top1") for row in pred_rows if row.get("reranked_top1")]
    gold_top = [row.get("gold_chunk_id") for row in pred_rows if row.get("gold_chunk_id")]
    report["rerank_uplift"] = rerank_uplift(baseline, reranked, gold_top)

    report["unit_number_capture"] = unit_number_capture(gold_rows, pred_rows)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
