"""Selection helpers for section headers."""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List

from .header_match import classify_line
from .header_score import THRESHOLD, score_candidate


def select_headers(
    lines: Iterable[Dict],
    units_present_fn: Callable[[str], bool],
) -> List[Dict]:
    """Return the subset of ``lines`` that meet the deterministic threshold."""

    selections: List[Dict] = []

    for line in lines:
        text = line.get("text_norm", "")
        classification = classify_line(text, line.get("caps_ratio", 0.0))
        if classification["kind"] == "none":
            continue

        features = line.get("features", {})
        score, parts = score_candidate(classification["kind"], features)

        if classification["kind"] == "label" and units_present_fn(text):
            score -= 0.6
            parts["units_penalty"] = -0.6

        meets_threshold = score >= THRESHOLD
        record = {
            **line,
            **classification,
            "score": score,
            "partials": parts,
            "meets_threshold": meets_threshold,
        }
        selections.append(record)

    return [record for record in selections if record["meets_threshold"]]


__all__ = ["select_headers"]
