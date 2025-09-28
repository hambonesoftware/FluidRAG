"""Regex heuristics for headers."""
from __future__ import annotations

import re
from typing import List, Tuple

from backend.app.contracts.chunking import Chunk

_HEADER_RE = re.compile(r"^(\d+(?:\.\d+)*)?\s*(.+)$")


def find_header_candidates(chunks: List[Chunk]) -> List[Tuple[Chunk, int]]:
    candidates: List[Tuple[Chunk, int]] = []
    for chunk in chunks:
        first_line = chunk.text.strip().splitlines()[0] if chunk.text.strip() else ""
        match = _HEADER_RE.match(first_line)
        if not match:
            continue
        numbering, title = match.groups()
        level = numbering.count(".") + 1 if numbering else 1
        if len(title.split()) <= 12:
            candidates.append((chunk, level))
    return candidates
