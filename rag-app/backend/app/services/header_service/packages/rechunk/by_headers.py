"""Rechunk chunks by headers."""
from __future__ import annotations

from typing import Dict, List

from backend.app.contracts.chunking import Chunk
from backend.app.contracts.headers import Header


def rechunk_by_headers(headers: List[Header], chunks: List[Chunk]) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {header.title: [] for header in headers}
    current = headers[0].title if headers else "Document"
    for chunk in sorted(chunks, key=lambda c: c.start):
        matching = next((header for header in headers if chunk.chunk_id == header.start_chunk), None)
        if matching:
            current = matching.title
        sections.setdefault(current, []).append(chunk.chunk_id)
    return sections
