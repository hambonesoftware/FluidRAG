"""Header prototype utilities for sectioning assists."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Tuple

import numpy as np

from .encoder import EmbeddingEncoder


@dataclass(frozen=True)
class Prototype:
    proto_id: str
    text: str
    vector: np.ndarray


HEADER_PROTOTYPES: Sequence[Tuple[str, str]] = (
    ("SEC.PURPOSE", "Purpose & Scope"),
    ("SEC.PERFORMANCE", "Performance Requirements"),
    ("SEC.REFERENCES", "References"),
    ("SEC.SAFETY", "Safety Requirements"),
    ("SEC.FAT_SAT", "FAT, SAT & Acceptance"),
    ("SEC.APPENDIX", "Appendix"),
)


def build_prototype_index(encoder: EmbeddingEncoder) -> List[Prototype]:
    texts = [text for _, text in HEADER_PROTOTYPES]
    vectors = encoder.embed_texts(texts)
    index: List[Prototype] = []
    for (proto_id, text), vector in zip(HEADER_PROTOTYPES, vectors, strict=False):
        index.append(Prototype(proto_id=proto_id, text=text, vector=vector))
    return index


def topk_header_prototypes(
    line_vector: np.ndarray, index: Iterable[Prototype], *, k: int = 3
) -> List[Tuple[str, float]]:
    if line_vector.size == 0:
        return []
    sims: List[Tuple[str, float]] = []
    for proto in index:
        score = float(np.dot(line_vector, proto.vector))
        sims.append((proto.proto_id, score))
    sims.sort(key=lambda item: item[1], reverse=True)
    return sims[:k]


__all__ = ["Prototype", "HEADER_PROTOTYPES", "build_prototype_index", "topk_header_prototypes"]
