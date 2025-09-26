"""CLI to build microchunk, section, and retrieval artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Sequence

import pandas as pd

from ingest import MicroChunk
from index import BM25Store, EmbeddingStore
from stages import build_stage_payload


def _load_stage_chunks(path: Path) -> List[Dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        chunks = payload.get("chunks") or payload.get("items") or []
    else:
        chunks = payload
    result: List[Dict[str, object]] = []
    for entry in chunks:
        if isinstance(entry, dict):
            result.append(entry)
    return result


def build_artifacts(docs_dir: Path, out_dir: Path, token_size: int, overlap: int) -> None:
    microchunks: List[MicroChunk] = []
    section_groups: Dict[str, List[Dict[str, object]]] = {}

    for path in sorted(docs_dir.glob("*.json")):
        doc_id = path.stem
        chunks = _load_stage_chunks(path)
        if not chunks:
            continue
        result = build_stage_payload(doc_id, chunks, token_size=token_size, overlap=overlap)
        microchunks.extend(result.microchunks)
        section_groups[doc_id] = result.section_groups

    if not microchunks:
        raise RuntimeError("No microchunks were generated; ensure the docs directory contains stage JSON files")

    out_dir.mkdir(parents=True, exist_ok=True)
    micro_df = pd.DataFrame(microchunks)
    micro_df.to_parquet(out_dir / "microchunks.parquet", index=False)

    sections_path = out_dir / "sections.jsonl"
    with sections_path.open("w", encoding="utf-8") as handle:
        for doc_id, groups in section_groups.items():
            for group in groups:
                record = {
                    "doc_id": doc_id,
                    "section_id": group.get("section_id"),
                    "section_title": group.get("title"),
                    "micro_ids": group.get("micro_ids", []),
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    embedding_store = EmbeddingStore(out_dir / "embeddings.parquet")
    embedding_store.build(microchunks)

    bm25_store = BM25Store(out_dir / "bm25.idx")
    bm25_store.build(microchunks)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build microchunk artifacts from stage JSON files")
    parser.add_argument("--docs", type=Path, required=True, help="Directory containing staged JSON files")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory to write cache artifacts")
    parser.add_argument(
        "--token-size",
        type=int,
        default=90,
        help="Target UF microchunk token size (default: 90)",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=12,
        help="Token overlap between adjacent UF microchunks (default: 12)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    build_artifacts(args.docs, args.out_dir, args.token_size, args.overlap)


if __name__ == "__main__":
    main()
