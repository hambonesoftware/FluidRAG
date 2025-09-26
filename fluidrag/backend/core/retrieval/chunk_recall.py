"""Chunk recall helpers scoped to selected sections."""
from __future__ import annotations

from typing import Dict, Iterable, List

import numpy as np


def recall_chunks(
    query_vector: np.ndarray,
    chunk_vectors_by_section: Dict[str, np.ndarray],
    chunk_meta_by_section: Dict[str, Iterable[Dict]],
    *,
    top_kprime: int = 40,
) -> List[Dict]:
    """Return chunk candidates ranked within their respective sections."""

    candidates: List[Dict] = []

    for section_id, matrix in chunk_vectors_by_section.items():
        if matrix.size == 0:
            continue

        sims = matrix @ query_vector
        count = min(len(sims), top_kprime)
        indices = np.argsort(-sims)[:count]
        meta_list = list(chunk_meta_by_section[section_id])
        for idx in indices:
            record = dict(meta_list[idx])
            record["section_id"] = section_id
            record["S"] = float(sims[idx])
            candidates.append(record)

    candidates.sort(key=lambda item: -item["S"])
    return candidates[:top_kprime]


__all__ = ["recall_chunks"]
