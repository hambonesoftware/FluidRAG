"""High-energy physics inspired scoring."""
from __future__ import annotations

from backend.app.contracts.chunking import Chunk


def energy_score(chunk: Chunk) -> float:
    momentum = sum(1 for ch in chunk.text if ch.isupper())
    mass = len(chunk.text) or 1
    return momentum / mass
