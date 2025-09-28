"""Graph inspired ranking."""
from __future__ import annotations

from backend.app.contracts.chunking import Chunk


def graph_score(chunk: Chunk) -> float:
    edges = chunk.text.count(" ")
    return edges / (len(chunk.text.split()) or 1)
