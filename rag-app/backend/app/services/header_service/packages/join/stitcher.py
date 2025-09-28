"""Stitch headers into hierarchy."""
from __future__ import annotations

from typing import List, Tuple

from backend.app.contracts.chunking import Chunk
from backend.app.contracts.headers import Header


def stitch_headers(scored: List[Tuple[Chunk, int, float]]) -> List[Header]:
    stitched: List[Header] = []
    for chunk, level, confidence in sorted(scored, key=lambda item: item[0].start):
        title_line = chunk.text.strip().splitlines()[0]
        stitched.append(
            Header(
                title=title_line,
                level=level,
                start_chunk=chunk.chunk_id,
                end_chunk=chunk.chunk_id,
                confidence=confidence,
            )
        )
    return stitched
