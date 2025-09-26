"""Deterministic scoring helpers for section header candidates."""
from __future__ import annotations

from typing import Dict, Tuple

THRESHOLD = 2.25


def score_candidate(kind: str, features: Dict[str, float]) -> Tuple[float, Dict[str, float]]:
    """Return the aggregate score and contributing weights for a header candidate.

    The scoring scheme mirrors the blueprint in the refactor spec. The returned
    dictionary captures each contributing term so that traces can expose why a
    header was or was not selected.
    """

    parts: Dict[str, float] = {}
    score = 0.0

    if kind == "numeric":
        parts["base_numeric"] = 2.0
        score += 2.0
    elif kind == "appendix":
        parts["base_appendix"] = 2.0
        score += 2.0
    elif kind == "label":
        parts["base_label"] = 0.8
        score += 0.8

    if features.get("bold", 0.0) >= 1.0:
        parts["bold"] = 1.4
        score += 1.4

    if features.get("font_sigma", 0.0) >= 0.8:
        parts["font_sigma"] = 1.0
        score += 1.0

    if features.get("font_z", 0.0) >= 0.8:
        parts["font_z"] = 0.6
        score += 0.6

    if kind == "label" and features.get("caps_ratio", 0.0) >= 0.7:
        parts["caps_assist"] = 0.4
        score += 0.4

    proto_sim = features.get("proto_sim_max", 0.0)
    if proto_sim > 0.0:
        proto_term = 0.8 * proto_sim
        parts["proto"] = proto_term
        score += proto_term

    p_header = features.get("p_header", 0.0)
    if p_header > 0.0:
        p_header_term = 0.6 * p_header
        parts["p_header"] = p_header_term
        score += p_header_term

    return score, parts


__all__ = ["THRESHOLD", "score_candidate"]
