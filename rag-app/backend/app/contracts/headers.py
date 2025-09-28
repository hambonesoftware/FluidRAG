"""Header enrichment contracts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(slots=True)
class Header:
    title: str
    level: int
    start_chunk: str
    end_chunk: str
    confidence: float


@dataclass(slots=True)
class HeaderArtifact:
    doc_id: str
    headers: List[Header]
    sections: Dict[str, List[str]]
