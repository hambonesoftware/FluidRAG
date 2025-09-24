"""Signal utilities for heuristic segmentation."""

from __future__ import annotations

import math
import re
from typing import Iterable, List, Optional, Sequence


def smoothed_entropy(values: Sequence[float], window: int = 2) -> List[float]:
    """Simple moving average smoothing."""
    if not values:
        return []
    window = max(1, int(window))
    out: List[float] = []
    for idx in range(len(values)):
        start = max(0, idx - window)
        end = min(len(values), idx + window + 1)
        slice_vals = values[start:end]
        out.append(sum(slice_vals) / len(slice_vals))
    return out


def delta_entropy(entropy: Sequence[float]) -> List[float]:
    """Return absolute delta vs previous value."""
    if not entropy:
        return []
    deltas: List[float] = [0.0]
    for prev, cur in zip(entropy, entropy[1:]):
        deltas.append(abs(cur - prev))
    return deltas


def embedding_drift(prev: Optional[Sequence[float]], cur: Optional[Sequence[float]]) -> float:
    """Cosine distance placeholder."""
    if prev is None or cur is None:
        return 0.0
    prev_vec = list(prev)
    cur_vec = list(cur)
    if len(prev_vec) != len(cur_vec) or not prev_vec:
        return 0.0
    dot = sum(p * c for p, c in zip(prev_vec, cur_vec))
    prev_norm = math.sqrt(sum(p * p for p in prev_vec))
    cur_norm = math.sqrt(sum(c * c for c in cur_vec))
    if prev_norm == 0 or cur_norm == 0:
        return 0.0
    cos = dot / (prev_norm * cur_norm)
    return max(0.0, 1.0 - cos)


def cluster_switch(prev: Optional[str], cur: Optional[str]) -> float:
    return 1.0 if prev is not None and cur is not None and prev != cur else 0.0


def regex_prior(line: str, patterns: Iterable[str]) -> float:
    line = line or ""
    score = 0.0
    for pat in patterns:
        if re.search(pat, line, re.IGNORECASE):
            score += 1.0
    return score


def numbering_score(line: str) -> float:
    if not line:
        return 0.0
    line = line.strip()
    score = 0.0
    if re.match(r"^[A-Z]*\d+[\).]\s", line):
        score += 1.0
    if re.match(r"^(Appendix|Table|Figure)\s", line, re.IGNORECASE):
        score += 0.5
    return score


def layout_score(meta: Optional[dict]) -> float:
    if not meta:
        return 0.0
    score = 0.0
    if meta.get("is_heading"):
        score += 1.0
    if meta.get("font_size", 0) > meta.get("body_font", 0):
        score += 0.5
    if meta.get("bold"):
        score += 0.2
    return score
