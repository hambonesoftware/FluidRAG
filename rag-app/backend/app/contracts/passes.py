"""RAG passes contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(slots=True)
class RetrievalHit:
    chunk_id: str
    score: float
    text: str
    metadata: Dict[str, str]


@dataclass(slots=True)
class PassResult:
    name: str
    hits: List[RetrievalHit]
    answer: Dict[str, str]


@dataclass(slots=True)
class PipelineResult:
    doc_id: str
    passes: List[PassResult]
