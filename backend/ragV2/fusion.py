"""Score fusion and evidence band selection helpers."""
from __future__ import annotations

import math
from typing import Dict, Iterable, List

from .config import CFG
from .types import EvidenceBand, EvidenceScore


def zscore(values: Dict[str, float]) -> Dict[str, float]:
    if not values:
        return {}
    series = list(values.values())
    mean = sum(series) / len(series)
    variance = sum((value - mean) ** 2 for value in series) / len(series)
    stddev = math.sqrt(max(variance, 1e-8))
    return {key: (value - mean) / stddev for key, value in values.items()}


def fuse_scores(
    std: Dict[str, float], flu: Dict[str, float], hep: Dict[str, float]
) -> Dict[str, EvidenceScore]:
    std_z = zscore(std)
    flu_z = zscore(flu)
    hep_z = zscore(hep)
    fused: Dict[str, EvidenceScore] = {}
    keys = set(std_z) | set(flu_z) | set(hep_z)
    for cid in keys:
        final = (
            CFG.w_std * std_z.get(cid, 0.0)
            + CFG.w_flu * flu_z.get(cid, 0.0)
            + CFG.w_hep * hep_z.get(cid, 0.0)
        )
        fused[cid] = EvidenceScore(
            standard=std.get(cid, 0.0),
            fluid=flu.get(cid, 0.0),
            hep=hep.get(cid, 0.0),
            final=final,
            signals={
                "z_std": std_z.get(cid, 0.0),
                "z_flu": flu_z.get(cid, 0.0),
                "z_hep": hep_z.get(cid, 0.0),
            },
        )
    return fused


def intersect_or_tightest_band(
    bands: Iterable[EvidenceBand], ordered: Iterable
) -> EvidenceBand:
    bands = list(bands)
    if not bands:
        raise ValueError("No bands provided")
    if len(bands) == 1:
        return bands[0]
    intersection = set(bands[0].band_chunk_ids)
    for band in bands[1:]:
        intersection &= set(band.band_chunk_ids)
    if intersection:
        covering = [
            band
            for band in bands
            if intersection.issubset(set(band.band_chunk_ids))
        ]
        if covering:
            covering.sort(key=lambda band: (len(band.band_chunk_ids), -band.confidence))
            return covering[0]
    ranked = sorted(
        bands,
        key=lambda band: (len(band.band_chunk_ids), -band.confidence),
    )
    return ranked[0]
