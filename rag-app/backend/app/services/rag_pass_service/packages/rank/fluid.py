"""Fluid dynamics inspired scoring."""
from __future__ import annotations

from backend.app.contracts.chunking import Chunk


def flow_score(chunk: Chunk) -> float:
    length = max(len(chunk.text.split()), 1)
    return 1.0 / length + chunk.features.get("uppercase_ratio", 0.0)
