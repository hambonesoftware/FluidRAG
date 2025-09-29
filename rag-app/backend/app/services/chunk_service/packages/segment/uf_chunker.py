"""Universal format chunking heuristics."""

from __future__ import annotations

from typing import Any

from .....util.logging import get_logger

logger = get_logger(__name__)


def _sentence_token_count(sentence: str) -> int:
    return len(sentence.split())


def _is_heading_sentence(sentence: str) -> bool:
    text = sentence.strip()
    if not text:
        return False
    words = text.split()
    if len(words) <= 6 and text.isupper():
        return True
    upper_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    return upper_ratio > 0.55 and len(words) <= 12


def uf_chunk(
    sentences: list[str] | None = None,
    typography: dict[str, Any] | None = None,
    target_tokens: int | None = None,
    overlap: int | None = None,
) -> list[dict[str, Any]]:
    """Produce UF micro-chunks with metadata."""
    sentences = sentences or []
    if not sentences:
        return []
    target_tokens = max(target_tokens or 90, 10)
    overlap_tokens = max(overlap or 12, 0)
    avg_tokens = sum(_sentence_token_count(s) for s in sentences) / max(
        len(sentences), 1
    )
    overlap_sentences = int(round(overlap_tokens / max(avg_tokens or 1, 1)))
    overlap_sentences = max(0, min(overlap_sentences, len(sentences) - 1))
    chunks: list[dict[str, Any]] = []
    start = 0
    while start < len(sentences):
        end = start
        token_total = 0
        while end < len(sentences) and token_total < target_tokens:
            token_total += _sentence_token_count(sentences[end])
            end += 1
            if end < len(sentences) and _is_heading_sentence(sentences[end]):
                break
        chunk_sentences = sentences[start:end]
        if not chunk_sentences:
            break
        chunk = {
            "text": " ".join(chunk_sentences),
            "sentence_start": start,
            "sentence_end": end - 1,
            "token_count": sum(_sentence_token_count(s) for s in chunk_sentences),
            "typography": {
                "avg_size": (typography or {}).get("avg_size", 0.0),
                "avg_weight": (typography or {}).get("avg_weight", 0.0),
            },
        }
        chunks.append(chunk)
        if end >= len(sentences):
            break
        next_start = max(end - overlap_sentences, start + 1)
        if next_start <= start:
            next_start = start + 1
        start = next_start
    logger.debug(
        "chunk.uf_chunk",
        extra={
            "chunks": len(chunks),
            "sentences": len(sentences),
            "target": target_tokens,
        },
    )
    return chunks
