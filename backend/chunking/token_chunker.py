"""Token-aware chunking helpers."""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Tuple

from tokens import encode

MICRO_MAX_TOKENS = 90
MICRO_OVERLAP_TOKENS = 12

_SENT_SPLIT = re.compile(r"(?<=[\.!\?])\s+(?=[A-Z0-9])")


def _sentences(text: str) -> List[str]:
    """Return a list of roughly sentence-sized strings from ``text``."""

    text = text.strip()
    if not text:
        return []
    return _SENT_SPLIT.split(text)


def _window_hard_wrap(tokens: List[int], max_tokens: int) -> List[Tuple[int, int]]:
    """Yield sliding token windows honouring the configured overlap."""

    spans: List[Tuple[int, int]] = []
    n = len(tokens)
    if n == 0:
        return spans
    step = max(1, max_tokens - MICRO_OVERLAP_TOKENS)
    start = 0
    while start < n:
        end = min(start + max_tokens, n)
        spans.append((start, end))
        if end >= n:
            break
        # ensure the next window overlaps the previous one by MICRO_OVERLAP_TOKENS
        next_start = max(end - MICRO_OVERLAP_TOKENS, start + 1)
        # guard against pathological cases where max_tokens < overlap
        if next_start <= start:
            next_start = start + step
        start = min(next_start, n)
    return spans


def micro_chunks_by_tokens(doc_text: str) -> List[Dict[str, object]]:
    """Split ``doc_text`` into <=90 token UF micro-chunks with overlap.

    The function first groups sentences until the budget would be exceeded and
    falls back to a hard token window when an individual sentence (or merged
    block) is still oversized. Overlap between consecutive hard-wrapped chunks
    is maintained to preserve local context.
    """

    sentences = _sentences(doc_text)
    chunks: List[Dict[str, object]] = []
    current_sentences: List[str] = []
    current_tokens: List[int] = []

    def _flush() -> None:
        nonlocal current_sentences, current_tokens
        if not current_sentences:
            return
        text = " ".join(current_sentences).strip()
        toks = encode(text)
        if len(toks) > MICRO_MAX_TOKENS:
            spans = _window_hard_wrap(toks, MICRO_MAX_TOKENS)
            for start, end in spans:
                chunks.append(
                    {
                        "text": text,
                        "token_count": end - start,
                        "note": "hard-wrapped window (token spans recorded)",
                        "token_span": [start, end],
                    }
                )
        else:
            chunks.append(
                {
                    "text": text,
                    "token_count": len(toks),
                    "note": "sentence-packed",
                }
            )
        current_sentences = []
        current_tokens = []

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        sentence_tokens = encode(sentence)
        if len(sentence_tokens) > MICRO_MAX_TOKENS:
            _flush()
            spans = _window_hard_wrap(sentence_tokens, MICRO_MAX_TOKENS)
            for start, end in spans:
                chunks.append(
                    {
                        "text": sentence,
                        "token_count": end - start,
                        "note": "oversize-sentence hard-wrap",
                        "token_span": [start, end],
                    }
                )
            continue
        if len(current_tokens) + len(sentence_tokens) > MICRO_MAX_TOKENS:
            _flush()
        current_sentences.append(sentence)
        current_tokens.extend(sentence_tokens)
        if len(current_tokens) >= MICRO_MAX_TOKENS:
            _flush()

    _flush()
    for chunk in chunks:
        if chunk.get("token_count", 0) > MICRO_MAX_TOKENS:
            raise AssertionError(
                f"Chunk exceeds {MICRO_MAX_TOKENS} tokens: {chunk.get('token_count')}"
            )
        # attach stable debug helpers
        text = str(chunk.get("text", ""))
        chunk.setdefault("text_preview", text[:240])
        chunk.setdefault(
            "text_hash",
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    return chunks


__all__ = [
    "MICRO_MAX_TOKENS",
    "MICRO_OVERLAP_TOKENS",
    "micro_chunks_by_tokens",
]
