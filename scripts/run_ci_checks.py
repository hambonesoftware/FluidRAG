#!/usr/bin/env python3
"""CI gate checks for FluidRAG v2 artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fluidrag.backend.core.validators.units import dimension_sanity


def _load_artifact(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _atomicity(records: Iterable[Dict]) -> bool:
    records = list(records)
    if not records:
        return True
    sentence_counts = [max(1, record.get("text", "").count(".")) for record in records]
    mean = sum(sentence_counts) / len(sentence_counts)
    return mean <= 1.05


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Run FluidRAG CI gates against a pipeline artifact.")
    parser.add_argument("artifact", help="Path to the JSON artifact emitted by run_pipeline")
    args = parser.parse_args(argv)

    artifact_path = Path(args.artifact)
    if not artifact_path.exists():
        print(f"[CI] artifact not found: {artifact_path}", file=sys.stderr)
        return 1

    data = _load_artifact(artifact_path)
    errors: List[str] = []

    header_trace = data.get("traces", {}).get("headers", [])
    for candidate in header_trace:
        if candidate.get("decision") == "selected" and not candidate.get("meets_threshold"):
            errors.append(
                f"Header gate violation at page {candidate.get('page')} line {candidate.get('line_idx')}: selected below threshold"
            )

    for gap in data.get("section_gaps", []):
        if "gap_reason" not in gap:
            errors.append(f"Appendix gap on page {gap.get('page')} missing gap_reason")

    retrieval = data.get("retrieval", {}) or {}
    section_cap = int(data.get("config", {}).get("retrieval", {}).get("section_cap", 3))
    extractions: List[Dict] = []
    for pass_name, payload in retrieval.items():
        final_chunks = payload.get("final_chunks", [])
        per_section: Dict[str, int] = defaultdict(int)
        for chunk in final_chunks:
            sec_id = chunk.get("section_id")
            if not sec_id:
                continue
            per_section[sec_id] += 1
            if per_section[sec_id] > section_cap:
                errors.append(
                    f"Section diversity violation in pass {pass_name}: section {sec_id} exceeds cap {section_cap}"
                )
        extractions.extend(payload.get("extractions", []))
        if not payload.get("deterministic", False):
            errors.append(f"Retrieval payload for pass {pass_name} not marked deterministic")

    if extractions:
        if not all(rec.get("page") is not None for rec in extractions):
            errors.append("Extraction provenance missing page assignment")
        if not all(rec.get("provenance", {}).get("bboxes") for rec in extractions):
            errors.append("Extraction provenance missing bounding boxes")
        if not _atomicity(extractions):
            errors.append("Atomicity check failed: average sentences per extraction > 1.05")
        unit_records = [rec for rec in extractions if rec.get("unit")]
        if unit_records:
            parsed = sum(1 for rec in unit_records if rec.get("op"))
            rate = parsed / len(unit_records)
            if rate < 0.95:
                errors.append(f"Unit parse rate below threshold: {rate:.2%}")
            for rec in unit_records:
                unit = rec.get("unit")
                if unit and not dimension_sanity(unit):
                    errors.append(f"Unknown unit dimension detected: {unit}")

    if errors:
        print("[CI] FAIL:")
        for err in errors:
            print(f" - {err}")
        return 1

    print("[CI] All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
