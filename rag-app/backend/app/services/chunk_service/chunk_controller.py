"""Chunk controller."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel

from backend.app.contracts.chunking import Chunk
from backend.app.util.errors import AppError

from .packages.features.typography import extract_typography
from .packages.index.local_vss import build_local_index
from .packages.segment.sentences import split_sentences
from .packages.segment.uf_chunker import uf_chunk


class ChunkInternal(BaseModel):
    doc_id: str
    chunks: List[Chunk]
    embeddings: Dict[str, List[float]]


def run_uf_chunking(*, doc_id: str, normalize_artifact: str) -> ChunkInternal:
    manifest_path = Path(normalize_artifact)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    text = "\n\n".join(manifest.get("pages", []))
    sentences = split_sentences(text)
    chunk_texts = uf_chunk(sentences)
    chunks: List[Chunk] = []
    cursor = 0
    chunk_map: Dict[str, str] = {}
    for idx, chunk_text in enumerate(chunk_texts):
        start = cursor
        cursor += len(chunk_text)
        chunk_id = f"{doc_id}-chunk-{idx}"
        features = extract_typography(chunk_text)
        chunk = Chunk(doc_id=doc_id, chunk_id=chunk_id, text=chunk_text, start=start, end=cursor, features=features)
        chunks.append(chunk)
        chunk_map[chunk_id] = chunk_text
    _, embeddings = build_local_index(chunk_map)
    chunks_path = manifest_path.parent / "chunks.jsonl"
    chunks_path.write_text(
        "\n".join(json.dumps(asdict(chunk), sort_keys=True) for chunk in chunks),
        encoding="utf-8",
    )
    embeddings_path = manifest_path.parent / "embeddings.json"
    embeddings_path.write_text(json.dumps(embeddings, sort_keys=True), encoding="utf-8")
    return ChunkInternal(doc_id=doc_id, chunks=chunks, embeddings=embeddings)


def handle_chunk_errors(e: Exception) -> None:
    if isinstance(e, AppError):
        raise e
    raise AppError(str(e)) from e
