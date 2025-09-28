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


@dataclass(slots=True)
class HeaderChunk:
    header_id: str
    chunk_id: str
    text: str
    page: int
