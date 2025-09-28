"""Local vector store builder for UF chunks."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .....adapters.vectors import BM25Index, FaissIndex
from .....util.logging import get_logger

logger = get_logger(__name__)

_HASH_DIMENSION = 16
_TOKEN_PATTERN = re.compile(r"\w+")


def _hash_embed(text: str, dim: int = _HASH_DIMENSION) -> list[float]:
    vector = [0.0] * dim
    tokens = _TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        return vector
    for token in tokens:
        index = hash(token) % dim
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def build_local_index(
    doc_id: str | None = None, chunks_path: str | None = None
) -> None:
    """Optionally build per-doc vector index."""
    if not chunks_path:
        return
    path = Path(chunks_path)
    if not path.exists():
        logger.warning("chunk.index.missing_chunks", extra={"path": chunks_path})
        return

    chunk_texts: list[str] = []
    chunk_vectors: list[list[float]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            text = record.get("text", "")
            chunk_texts.append(text)
            chunk_vectors.append(_hash_embed(text))

    bm25 = BM25Index()
    if chunk_texts:
        bm25.add(chunk_texts)
    index_dir = path.parent
    index_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "doc_id": doc_id,
        "chunk_count": len(chunk_texts),
        "bm25_docs": len(chunk_texts),
        "dense_index_path": None,
    }

    if chunk_vectors:
        dense_path = index_dir / "vectors.faiss.json"
        faiss = FaissIndex(len(chunk_vectors[0]), str(dense_path))
        faiss.add(chunk_vectors)
        faiss.save()
        manifest["dense_index_path"] = str(dense_path)

    manifest_path = index_dir / "index.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    logger.info(
        "chunk.index.built",
        extra={
            "doc_id": doc_id,
            "chunks": len(chunk_texts),
            "dense": bool(chunk_vectors),
            "path": str(manifest_path),
        },
    )
