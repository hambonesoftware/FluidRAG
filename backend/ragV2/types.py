"""Data structures shared across the RAG v2 pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # pragma: no cover - optional dependency
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - fallback when numpy is unavailable
    np = None  # type: ignore


EmbedT = Optional["np.ndarray"] if np is not None else Optional[Sequence[float]]


@dataclass
class Chunk:
    """A slice of source material considered during retrieval and synthesis."""

    chunk_id: str
    doc_id: str
    section_no: Optional[str]
    section_title: Optional[str]
    page_range: Tuple[int, int]
    text: str
    embed: EmbedT = None
    bm25: Optional[float] = None
    regex_hits: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)
    stage_tag: str = "STANDARD"
    break_score: float = 0.0
    header_candidate: bool = False
    resolution: str = "micro"
    retrieval_scores: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.meta = dict(self.meta or {})
        self.stage_tag = str(self.stage_tag or "STANDARD").upper()
        self.resolution = str(self.resolution or "micro").lower()
        if self.retrieval_scores is None:
            self.retrieval_scores = {}


@dataclass
class EvidenceScore:
    """Score contributions from each micro-agent plus the fused score."""

    standard: float = 0.0
    fluid: float = 0.0
    hep: float = 0.0
    final: float = 0.0
    signals: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceBand:
    """A contiguous (or virtual contiguous) evidence window around a seed chunk."""

    seed_chunk_id: str
    start_idx: int
    end_idx: int
    confidence: float
    entropy_trace_left: List[float]
    entropy_trace_right: List[float]
    method: str
    band_chunk_ids: List[str]

    def __post_init__(self) -> None:
        self.entropy_trace_left = list(self.entropy_trace_left)
        self.entropy_trace_right = list(self.entropy_trace_right)
        self.band_chunk_ids = list(self.band_chunk_ids)


@dataclass
class ExtractionField:
    """Single extracted field with citation information."""

    text: str
    cite: str
    value: Optional[Any] = None


@dataclass
class ExtractionJSON:
    """Structured extraction payload returned by the orchestrator."""

    requirements: List[ExtractionField] = field(default_factory=list)
    thresholds: List[ExtractionField] = field(default_factory=list)
    units: List[ExtractionField] = field(default_factory=list)
    standards: List[Dict[str, Any]] = field(default_factory=list)
    exceptions: List[ExtractionField] = field(default_factory=list)
    acceptance_criteria: List[ExtractionField] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    confidence: float = 0.0
    provenance: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dictionary useful for logging or JSON encoding."""

        def _serialize_field(item: ExtractionField) -> Dict[str, Any]:
            data: Dict[str, Any] = {"text": item.text, "cite": item.cite}
            if item.value is not None:
                data["value"] = item.value
            return data

        return {
            "requirements": [_serialize_field(f) for f in self.requirements],
            "thresholds": [_serialize_field(f) for f in self.thresholds],
            "units": [_serialize_field(f) for f in self.units],
            "standards": list(self.standards),
            "exceptions": [_serialize_field(f) for f in self.exceptions],
            "acceptance_criteria": [
                _serialize_field(f) for f in self.acceptance_criteria
            ],
            "conflicts": list(self.conflicts),
            "missing": list(self.missing),
            "confidence": self.confidence,
            "provenance": dict(self.provenance),
        }
