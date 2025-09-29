"""Fluid-inspired heuristic ranking."""

from __future__ import annotations

from typing import Any


def flow_score(chunk: dict[str, Any]) -> float:
    """Fluid-inspired flow scoring based on continuity & gradients."""

    length = float(chunk.get("token_count") or len(str(chunk.get("text", "")).split()))
    sentence_span = (
        int(chunk.get("sentence_end", 0)) - int(chunk.get("sentence_start", 0)) + 1
    )
    sentence_span = max(sentence_span, 1)
    continuity = 1.0 / sentence_span
    return round(length * 0.05 + continuity, 4)


__all__ = ["flow_score"]
