"""Compose context windows for prompts."""
from __future__ import annotations

from typing import Dict, List

from backend.app.contracts.chunking import Chunk


def compose_window(chunks: Dict[str, Chunk], chunk_ids: List[str]) -> str:
    ordered = [chunks[cid].text for cid in chunk_ids if cid in chunks]
    return "\n\n".join(ordered)
