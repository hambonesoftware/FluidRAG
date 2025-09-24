from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, List, Sequence

from fluidrag.src.chunking.standard import Chunk

NUMERIC_REGEX = re.compile(r"[-+]?\d+(?:\.\d+)?")
STANDARD_REGEX = re.compile(r"\b(?:ISO|IEC|NFPA|UL|IEEE|EN)\s?[0-9A-Za-z:\-]+\b", re.IGNORECASE)
CLAUSE_REGEX = re.compile(r"\b\d+(?:\.\d+){1,}\b")
BULLET_REGEX = re.compile(r"^[\s\-\*•]+\w+")
REFERENCE_REGEX = re.compile(r"\b(?:see|per|ref(erence)?)\b", re.IGNORECASE)
RISK_TERMS = {"hazard", "safety", "risk", "danger", "sil", "pl"}
ACCEPTANCE_TERMS = {"fat", "sat", "accept", "verify", "accuracy", "tolerance"}
MUST_TERMS = {"shall", "must", "required", "ensure"}
BOILERPLATE_TERMS = {"warranty", "liability", "general"}


def _tokenize(text: str) -> List[str]:
    return [tok.lower() for tok in re.findall(r"[A-Za-z0-9%]+", text)]


def shannon_entropy(tokens: Sequence[str]) -> float:
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    total = len(tokens)
    entropy = -sum((cnt / total) * math.log(cnt / total, 2) for cnt in counts.values())
    max_entropy = math.log(len(counts) or 1, 2)
    if max_entropy == 0:
        return 0.0
    return entropy / max_entropy


def smooth_series(values: Sequence[float], window: int = 3) -> List[float]:
    if not values:
        return []
    smoothed: List[float] = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        window_vals = values[start : i + 1]
        smoothed.append(sum(window_vals) / len(window_vals))
    return smoothed


def cosine_similarity(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[token] * b.get(token, 0) for token in a)
    if dot == 0:
        return 0.0
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def compute_signals(chunks: Sequence[Chunk]) -> None:
    tokenized = [_tokenize(chunk.text) for chunk in chunks]
    entropies = [shannon_entropy(tokens) for tokens in tokenized]
    entropy_smooth = smooth_series(entropies, window=3)
    d_entropy = [abs(entropy_smooth[i] - entropy_smooth[i - 1]) if i > 0 else 0.0 for i in range(len(entropy_smooth))]

    prev_counter: Counter | None = None
    prev_section: str | None = None
    for idx, chunk in enumerate(chunks):
        tokens = tokenized[idx]
        counter = Counter(tokens)
        if prev_counter is None:
            emb_drift = 0.0
        else:
            emb_drift = 1.0 - cosine_similarity(prev_counter, counter)
        cluster_switch = 0
        if prev_section is not None and chunk.section_number is not None and chunk.section_number != prev_section:
            cluster_switch = 1
        regex_prior = 1.0 if CLAUSE_REGEX.search(chunk.text.split("\n", 1)[0]) else 0.0
        numbering_score = 0.0
        if prev_section and chunk.section_number:
            try:
                prev_num = float(prev_section.split(".")[0])
                cur_num = float(chunk.section_number.split(".")[0])
                numbering_score = 1.0 if cur_num - prev_num in {0.0, 1.0} else 0.2
            except ValueError:
                numbering_score = 0.5
        layout_score = 0.0

        chunk.signals.update(
            {
                "entropy": entropies[idx],
                "entropy_smooth": entropy_smooth[idx],
                "d_entropy": d_entropy[idx],
                "emb_drift": min(max(emb_drift, 0.0), 1.0),
                "cluster_switch": cluster_switch,
                "regex_prior": regex_prior,
                "numbering_score": numbering_score,
                "layout_score": layout_score,
            }
        )
        prev_counter = counter
        prev_section = chunk.section_number or prev_section


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _list_density(text: str) -> float:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0
    bullets = sum(1 for line in lines if BULLET_REGEX.match(line.strip()))
    return bullets / len(lines)


def _reference_density(text: str) -> float:
    tokens = _tokenize(text)
    if not tokens:
        return 0.0
    refs = sum(1 for token in tokens if REFERENCE_REGEX.match(token))
    return refs / len(tokens)


def _connectivity(idx: int, counters: Sequence[Counter]) -> float:
    cur = counters[idx]
    prev_sim = cosine_similarity(cur, counters[idx - 1]) if idx > 0 else 0.0
    next_sim = cosine_similarity(cur, counters[idx + 1]) if idx < len(counters) - 1 else 0.0
    return max(prev_sim, 0.0) * 0.5 + max(next_sim, 0.0) * 0.5


def compute_scores(chunks: Sequence[Chunk], config: dict) -> None:
    compute_signals(chunks)
    weights = config["scores"]["weights"]
    thresholds = config["scores"]["thresholds"]

    counters = [Counter(_tokenize(chunk.text)) for chunk in chunks]
    entropies = [chunk.signals.get("entropy", 0.0) for chunk in chunks]

    for idx, chunk in enumerate(chunks):
        signals = chunk.signals
        break_weights = weights["break"]
        break_score = (
            break_weights["wH"] * signals.get("d_entropy", 0.0)
            + break_weights["wD"] * signals.get("emb_drift", 0.0)
            + break_weights["wC"] * signals.get("cluster_switch", 0.0)
            + break_weights["wR"] * signals.get("regex_prior", 0.0)
            + break_weights["wN"] * signals.get("numbering_score", 0.0)
            + break_weights["wL"] * signals.get("layout_score", 0.0)
        )

        tokens = _tokenize(chunk.text)
        len_norm = _clamp(len(tokens) / 90.0)
        list_density = _clamp(_list_density(chunk.text))
        ref_density = _clamp(_reference_density(chunk.text) * 3)
        standards_presence = 1.0 if STANDARD_REGEX.search(chunk.text) else 0.0
        connectivity = _clamp(_connectivity(idx, counters))
        numeric_tokens = sum(1 for token in tokens if NUMERIC_REGEX.match(token))
        numeric_only = -1.0 if tokens and numeric_tokens / len(tokens) > 0.6 else 0.0

        fluid_weights = weights["fluid"]
        fluid_score_raw = (
            fluid_weights["len"] * len_norm
            + fluid_weights["list"] * list_density
            + fluid_weights["ref"] * ref_density
            + fluid_weights["conn"] * connectivity
            + fluid_weights["std"] * standards_presence
            + fluid_weights["numeric_only"] * numeric_only
        )
        fluid_score = _clamp(fluid_score_raw)

        numeric_density = 1.0 if numeric_tokens else 0.0
        norm_count = sum(1 for token in tokens if token in MUST_TERMS)
        constraint_strength = 1.0 if norm_count else 0.0
        acceptance_density = _clamp(sum(1 for token in tokens if token in ACCEPTANCE_TERMS) / max(len(tokens), 1) * 3.0)
        risk_density = _clamp(sum(1 for token in tokens if token in RISK_TERMS) / max(len(tokens), 1) * 3.0)
        boiler_density = sum(1 for token in tokens if token in BOILERPLATE_TERMS) / max(len(tokens), 1)

        hep_weights = weights["hep"]
        hep_score_raw = (
            hep_weights["num"] * numeric_density
            + hep_weights["must"] * constraint_strength
            + hep_weights["acc"] * acceptance_density
            + hep_weights["risk"] * risk_density
            + hep_weights["ent"] * entropies[idx]
            + hep_weights["boiler"] * boiler_density
        )
        # Normalize by positive weight sum to keep range in 0..1 before clamping
        positive_sum = sum(max(0.0, w) for w in hep_weights.values())
        if positive_sum:
            hep_score_raw /= positive_sum
        hep_score = _clamp(hep_score_raw)

        chunk.scores.update(
            {
                "break_score": _clamp(break_score),
                "fluid_score": fluid_score,
                "hep_score": hep_score,
            }
        )

        chunk.graph.setdefault("standard_refs", [])
        chunk.graph.setdefault("clause_refs", [])
        chunk.graph.setdefault("quantity_ids", [])
        chunk.graph.setdefault("communities", [])

    # Apply threshold flags to help retrieval views
    for chunk in chunks:
        chunk.scores["fluid_above_threshold"] = chunk.scores.get("fluid_score", 0.0) >= thresholds["fluid"]
        chunk.scores["hep_above_threshold"] = chunk.scores.get("hep_score", 0.0) >= thresholds["hep"]


__all__ = ["compute_signals", "compute_scores", "smooth_series", "shannon_entropy"]
