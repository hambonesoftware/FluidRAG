"""Section pre-filter helpers for retrieval."""
from __future__ import annotations

from typing import Dict, Iterable, List

import numpy as np


def prefilter_sections(
    query_vector: np.ndarray,
    section_vectors: np.ndarray,
    section_meta: Iterable[Dict],
    *,
    top_m: int = 15,
) -> List[Dict]:
    """Return the top-M sections ranked by cosine similarity."""

    if section_vectors.size == 0:
        return []

    sims = section_vectors @ query_vector
    indices = np.argsort(-sims)[:top_m]
    meta_list = list(section_meta)
    return [dict(meta_list[idx], S=float(sims[idx])) for idx in indices]


__all__ = ["prefilter_sections"]
