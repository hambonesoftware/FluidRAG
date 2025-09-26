"""Score fusion helpers for retrieval."""
from __future__ import annotations

from typing import Mapping


def fuse(score_s: float, score_e: float, score_f: float, score_h: float, weights: Mapping[str, float]) -> float:
    """Combine the component scores using the configured weights.

    Parameters
    ----------
    score_s, score_e, score_f, score_h:
        Component scores (section relevance, entropy, flow, heuristics).
    weights:
        Mapping containing ``alpha``, ``beta``, ``gamma`` and ``delta`` keys.

    Returns
    -------
    float
        Weighted sum of the components. Missing weights default to zero which
        keeps the helper resilient while the configuration is evolving.
    """

    alpha = float(weights.get("alpha", 0.0))
    beta = float(weights.get("beta", 0.0))
    gamma = float(weights.get("gamma", 0.0))
    delta = float(weights.get("delta", 0.0))
    return (alpha * score_s) + (beta * score_e) + (gamma * score_f) + (delta * score_h)


__all__ = ["fuse"]
