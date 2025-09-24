"""Multi-signal header detection utilities used by the FluidRAG pipeline."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence

try:  # pragma: no cover - optional dependency
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - fallback when numpy is unavailable
    np = None  # type: ignore

from .config import CFG

HEADER_REGEX = re.compile(
    r"^(?:[A-Z][A-Z\s\d\-:]{2,}|\d+(?:\.\d+)*\s+[A-Z][^\n]+)$"
)
NUMBERING_REGEX = re.compile(r"^(?P<num>\d+(?:\.\d+)*)")


def _entropy(text: str) -> float:
    tokens = [token.lower() for token in re.findall(r"\w+", text or "")]
    if not tokens:
        return 0.0
    counts: Dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    total = len(tokens)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log(max(p, 1e-9))
    return entropy / math.log(total + 1)


def _cosine_distance(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    if np is None:
        # minimal cosine distance implementation without numpy
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
    else:  # pragma: no cover - uses numpy when available
        arr_a = np.asarray(vec_a)
        arr_b = np.asarray(vec_b)
        dot = float(arr_a.dot(arr_b))
        norm_a = float(np.linalg.norm(arr_a))
        norm_b = float(np.linalg.norm(arr_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    cosine = max(min(dot / (norm_a * norm_b), 1.0), -1.0)
    return 1.0 - cosine


def _moving_average(values: Sequence[float], window: int) -> List[float]:
    if window <= 1:
        return list(values)
    averaged: List[float] = []
    for idx in range(len(values)):
        start = max(0, idx - window + 1)
        slice_values = values[start : idx + 1]
        averaged.append(sum(slice_values) / len(slice_values))
    return averaged


def _local_maxima(scores: Sequence[float]) -> List[int]:
    peaks: List[int] = []
    for idx, score in enumerate(scores):
        prev_score = scores[idx - 1] if idx > 0 else score
        next_score = scores[idx + 1] if idx + 1 < len(scores) else score
        if score >= prev_score and score >= next_score:
            peaks.append(idx)
    return peaks


@dataclass
class HeaderSignal:
    """Container for the per-chunk signal breakdown."""

    entropy_jump: float
    embedding_drift: float
    cluster_switch: float
    regex_prior: float
    numbering_score: float
    layout_score: float
    break_score: float


class HeaderDetector:
    """Compute break scores for a sequence of chunks using multiple signals."""

    def __init__(self, *, enable_pelt: bool | None = None) -> None:
        self._enable_pelt = CFG.enable_pelt if enable_pelt is None else bool(enable_pelt)

    def _compute_signals(self, chunks: Sequence[Dict]) -> List[HeaderSignal]:
        entropies = [_entropy(chunk.get("text", "")) for chunk in chunks]
        smooth = _moving_average(entropies, max(1, CFG.header_entropy_window))
        entropy_jumps = [abs(curr - smooth[idx - 1]) if idx else curr for idx, curr in enumerate(smooth)]

        signals: List[HeaderSignal] = []
        prev_cluster = None
        prev_number = None
        prev_embed: Sequence[float] | None = None
        for idx, chunk in enumerate(chunks):
            embed = chunk.get("embed") or chunk.get("embedding")
            if embed is None:
                emb_drift = 0.0
            else:
                if prev_embed is None:
                    emb_drift = 0.0
                else:
                    emb_drift = _cosine_distance(prev_embed, embed)
                prev_embed = embed

            cluster_id = chunk.get("cluster_id")
            cluster_switch = 1.0 if prev_cluster is not None and cluster_id != prev_cluster else 0.0
            prev_cluster = cluster_id

            heading_line = (chunk.get("header") or chunk.get("section_name") or "").strip()
            if not heading_line:
                heading_line = chunk.get("text", "").splitlines()[0] if chunk.get("text") else ""
            regex_prior = 1.0 if HEADER_REGEX.match(heading_line.strip()) else 0.0

            number_match = NUMBERING_REGEX.match(heading_line.strip())
            numbering = number_match.group("num") if number_match else None
            numbering_score = 0.0
            if numbering:
                numbering_parts = [int(part) for part in numbering.split(".") if part.isdigit()]
                if prev_number is None:
                    numbering_score = 0.5
                else:
                    try:
                        increment = numbering_parts[-1] - prev_number[-1]
                        numbering_score = 1.0 if increment in (0, 1) else 0.25
                    except Exception:
                        numbering_score = 0.25
                prev_number = numbering_parts or prev_number
            layout_meta = chunk.get("layout_score") or chunk.get("meta", {}).get("layout_score")
            layout_score = float(layout_meta) if layout_meta is not None else 0.0

            break_score = (
                CFG.header_weight_entropy * entropy_jumps[idx]
                + CFG.header_weight_drift * emb_drift
                + CFG.header_weight_cluster * cluster_switch
                + CFG.header_weight_regex * regex_prior
                + CFG.header_weight_numbering * numbering_score
                + CFG.header_weight_layout * layout_score
            )
            signals.append(
                HeaderSignal(
                    entropy_jump=entropy_jumps[idx],
                    embedding_drift=emb_drift,
                    cluster_switch=cluster_switch,
                    regex_prior=regex_prior,
                    numbering_score=numbering_score,
                    layout_score=layout_score,
                    break_score=break_score,
                )
            )
        return signals

    def detect(self, chunks: Sequence[Dict]) -> List[int]:
        """Return the chunk indices that qualify as headers."""

        if not chunks:
            return []
        signals = self._compute_signals(chunks)
        scores = [signal.break_score for signal in signals]
        peaks = _local_maxima(scores)
        threshold = CFG.header_threshold
        min_gap = max(1, CFG.header_min_gap)

        selected: List[int] = []
        last_idx = -min_gap
        for idx in peaks:
            if scores[idx] < threshold:
                continue
            if idx - last_idx < min_gap:
                # keep the higher score when within the exclusion window
                if selected and scores[idx] > scores[selected[-1]]:
                    selected[-1] = idx
                    last_idx = idx
                continue
            selected.append(idx)
            last_idx = idx

        if self._enable_pelt and len(scores) > 3:
            try:  # pragma: no cover - optional dependency path
                import ruptures as rpt  # type: ignore

                algo = rpt.Pelt(model="rbf").fit(scores)
                change_points = algo.predict(pen=1)
                for idx in change_points:
                    idx = max(0, min(idx - 1, len(scores) - 1))
                    if scores[idx] >= threshold:
                        selected.append(idx)
            except Exception:
                # fall back silently when ruptures is unavailable
                pass

        selected = sorted(set(selected))

        for idx, chunk in enumerate(chunks):
            signal = signals[idx]
            meta = dict(chunk.get("meta") or {})
            meta.setdefault("header_signals", {})
            meta["header_signals"].update(
                {
                    "entropy_jump": signal.entropy_jump,
                    "embedding_drift": signal.embedding_drift,
                    "cluster_switch": signal.cluster_switch,
                    "regex_prior": signal.regex_prior,
                    "numbering_score": signal.numbering_score,
                    "layout_score": signal.layout_score,
                    "break_score": signal.break_score,
                    "is_boundary": idx in selected,
                }
            )
            chunk["meta"] = meta
            chunk["break_score"] = signal.break_score
            chunk["header_candidate"] = idx in selected

        return selected


def attach_stage_tag(chunks: Iterable[Dict], stage_tag: str) -> None:
    """Mutate chunks in-place, ensuring the stage tag is present and normalised."""

    tag = stage_tag.upper()
    for chunk in chunks:
        chunk["stage_tag"] = tag
        chunk.setdefault("meta", {}).setdefault("stage_tag", tag)

