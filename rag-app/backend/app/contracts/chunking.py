"""Chunking stage contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(slots=True)
class Chunk:
    doc_id: str
    chunk_id: str
    text: str
    start: int
    end: int
    features: Dict[str, float]


@dataclass(slots=True)
class ChunkCollection:
    doc_id: str
    chunks: List[Chunk]
