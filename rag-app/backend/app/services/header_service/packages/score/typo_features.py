"""Typography-based scoring heuristics for headers."""

from __future__ import annotations

from typing import Any

from .....util.logging import get_logger

logger = get_logger(__name__)


def score_typo(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add typography-derived confidence."""

    for candidate in candidates:
        typography = candidate.get("typography") or {}
        size = float(typography.get("avg_size", 0) or 0)
        weight = float(typography.get("avg_weight", 0) or 0)
        boost = 0.0
        if size >= 16:
            boost += 0.2
        elif size >= 13:
            boost += 0.1
        if weight >= 600:
            boost += 0.1
        if candidate.get("score", 0.0) >= 0.75 and size >= 14:
            boost += 0.05
        if boost:
            candidate["score_typography"] = boost
            candidate["score"] = min(1.0, float(candidate.get("score", 0.0)) + boost)
        else:
            candidate.setdefault("score_typography", 0.0)
    logger.debug(
        "headers.score.typography",
        extra={
            "candidates": len(candidates),
            "boosted": sum(
                1 for cand in candidates if cand.get("score_typography", 0.0) > 0.0
            ),
        },
    )
    return candidates


__all__ = ["score_typo"]
