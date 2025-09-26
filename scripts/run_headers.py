#!/usr/bin/env python3
"""Run the header pipeline against a decomposed document JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from backend.headers.pipeline import run_headers


def _load_decomp(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
        if not isinstance(data, dict):  # pragma: no cover - defensive
            raise ValueError("Document decomposition must be a JSON object")
        return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the FluidRAG header pipeline")
    parser.add_argument("--doc", required=True, help="Path to a decomposed document JSON file")
    parser.add_argument(
        "--out",
        help="Directory for header artifacts. Defaults to artifacts/<doc_id>.",
    )
    parser.add_argument("--doc-id", help="Override the document identifier")
    args = parser.parse_args()

    doc_path = Path(args.doc)
    if not doc_path.exists():
        raise FileNotFoundError(f"Document decomposition file not found: {doc_path}")

    decomp = _load_decomp(doc_path)
    doc_id = args.doc_id or str(decomp.get("doc_id") or doc_path.stem)
    output_dir = Path(args.out) if args.out else Path("artifacts") / doc_id
    decomp["output_dir"] = str(output_dir)

    result = run_headers(doc_id, decomp)

    summary = {
        "doc_id": result.doc_id,
        "output_dir": str(result.output_dir),
        "uf_chunk_count": len(result.uf_chunks),
        "efhg_span_count": len(result.spans),
        "header_count": len(result.headers),
        "header_shard_count": len(result.header_shards),
        "candidate_audit": str(result.output_dir / "candidate_audit.json"),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
