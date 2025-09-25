"""Rebuild retrieval indexes from uploaded documents."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from backend.chunking.atomic_chunker import AtomicChunker
from backend.chunking.macro_chunker import MacroChunker
from backend.indexes.clause_index import ClauseIndex
from backend.retrieval.retrieval import load_retriever
from fluidrag.config import load_config


def _load_pages(path: Path) -> List[Dict[str, object]]:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    text = path.read_text(encoding="utf-8")
    pages = [segment.strip() for segment in text.split("\f") if segment.strip()]
    if not pages:
        pages = [text]
    return [{"page": idx + 1, "text": page} for idx, page in enumerate(pages)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Reindex FluidRAG documents")
    parser.add_argument("--doc", type=Path, required=True, help="Path to document text or JSON")
    parser.add_argument("--config", type=Path, default=Path("config/fluidrag.yaml"))
    args = parser.parse_args()

    cfg = load_config(args.config)
    chunk_cfg = (cfg.get("chunking", {}) or {}).get("micro", {})
    macro_cfg = (cfg.get("chunking", {}) or {}).get("macro", {})

    doc_id = args.doc.stem
    pages = _load_pages(args.doc)

    chunker = AtomicChunker(chunk_cfg)
    micro_chunks = chunker.chunk(doc_id, pages, [])

    macro_chunker = MacroChunker(macro_cfg)
    macro_chunks = macro_chunker.build(micro_chunks)

    clause_index = ClauseIndex()
    retriever = load_retriever(clause_index, config_path=args.config)
    macro_map = {macro["macro_id"]: macro.get("micro_children", []) for macro in macro_chunks}
    retriever.index(micro_chunks, macro_map=macro_map)

    output_dir = Path("index")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{doc_id}_micro.json").write_text(
        json.dumps(micro_chunks, indent=2), encoding="utf-8"
    )
    (output_dir / f"{doc_id}_macro.json").write_text(
        json.dumps(macro_chunks, indent=2), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "doc_id": doc_id,
                "micro_chunks": len(micro_chunks),
                "macro_chunks": len(macro_chunks),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
