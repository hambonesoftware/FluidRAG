"""Feature computation for header candidates."""
from __future__ import annotations

from typing import Dict, Iterable, List, Sequence, Tuple


def compute_features(
    line: Dict,
    prototype_similarities: Sequence[Tuple[str, float]],
    p_header: float | None = None,
) -> Dict:
    """Return a deterministic feature dictionary for a line candidate."""

    sims = sorted(prototype_similarities, key=lambda item: item[1], reverse=True)
    top3 = sims[:3]

    return {
        "bold": 1.0 if line.get("bold") else 0.0,
        "font_sigma": float(line.get("font_sigma_rank") or 0.0),
        "font_z": float(line.get("font_size_z") or 0.0),
        "caps_ratio": float(line.get("caps_ratio") or 0.0),
        "len": len(line.get("text_norm", "")),
        "proto_sim_max": top3[0][1] if top3 else 0.0,
        "proto_top3": top3,
        "p_header": float(p_header or 0.0),
    }


__all__ = ["compute_features"]
