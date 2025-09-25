"""Utility helpers shared across retrieval modules."""
from __future__ import annotations

import hashlib
import math
import re
from typing import Dict, List, Sequence

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)?")


def tokenize(text: str) -> List[str]:
    return [token.lower() for token in _TOKEN_RE.findall(text)]


def vectorize_tokens(tokens: Sequence[str], dim: int = 256) -> List[float]:
    vec = [0.0] * dim
    if not tokens:
        return vec
    for token in tokens:
        digest = hashlib.sha1(token.encode()).digest()
        idx = digest[0] % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(value * value for value in vec)) or 1.0
    return [value / norm for value in vec]


def normalize_scores(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    values = list(scores.values())
    min_v = min(values)
    max_v = max(values)
    if math.isclose(min_v, max_v):
        return {key: 0.5 for key in scores}
    scale = max_v - min_v
    return {key: (value - min_v) / scale for key, value in scores.items()}


__all__ = ["tokenize", "vectorize_tokens", "normalize_scores"]
