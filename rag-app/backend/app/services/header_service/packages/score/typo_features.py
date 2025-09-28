"""Score headers using typography features."""
from __future__ import annotations

from typing import Tuple

from backend.app.contracts.chunking import Chunk


def score_typo(candidate: Tuple[Chunk, int]) -> Tuple[Chunk, int, float]:
    chunk, level = candidate
    features = chunk.features
    confidence = 0.5
    confidence += features.get("uppercase_ratio", 0.0) * 0.5
    confidence += features.get("bullet_ratio", 0.0) * -0.5
    return chunk, level, max(0.0, min(1.0, confidence))
