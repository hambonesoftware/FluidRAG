"""Uniform chunking."""
from __future__ import annotations

from typing import Iterable, List


def uf_chunk(sentences: Iterable[str], *, target_tokens: int = 90, overlap: int = 10) -> List[str]:
    buffer: List[str] = []
    chunks: List[str] = []
    current_tokens = 0
    for sentence in sentences:
        tokens = sentence.split()
        if current_tokens + len(tokens) > target_tokens and buffer:
            chunks.append(" ".join(buffer))
            buffer = buffer[-overlap:] if overlap else []
            current_tokens = sum(len(item.split()) for item in buffer)
        buffer.append(sentence)
        current_tokens += len(tokens)
    if buffer:
        chunks.append(" ".join(buffer))
    return chunks
