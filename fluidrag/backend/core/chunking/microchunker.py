"""Micro-chunk generation utilities."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, List, Tuple


@dataclass
class ChunkWindow:
    """Metadata describing a chunk emitted by :func:`microchunk`.

    Attributes
    ----------
    start:
        Character offset of the chunk relative to the section text.
    end:
        Exclusive end offset of the chunk relative to the section text.
    text:
        The chunk text itself.
    """

    start: int
    end: int
    text: str


def _split_sentences(text: str) -> List[Tuple[int, str]]:
    """Return a list of ``(offset, sentence)`` pairs for ``text``."""

    sentences: List[Tuple[int, str]] = []
    for match in re.finditer(r"[^.!?]+[.!?]?", text):
        sentence = match.group(0).strip()
        if not sentence:
            continue
        sentences.append((match.start(), sentence))

    if not sentences and text:
        sentences.append((0, text.strip()))

    return sentences


def microchunk(
    section_text: str,
    *,
    window_chars: int = 450,
    stride_chars: int = 80,
) -> Iterator[ChunkWindow]:
    """Yield overlapping window chunks for ``section_text``.

    The implementation prefers to align boundaries to sentence (and simple
    bullet) edges. Offsets are calculated relative to the raw section text so
    that downstream provenance can reference the same coordinate system.
    """

    if not section_text:
        return

    sentences = _split_sentences(section_text)
    if not sentences:
        return

    start_idx = 0
    n_sentences = len(sentences)

    while start_idx < n_sentences:
        start_offset = sentences[start_idx][0]
        chunk_parts: List[str] = []
        end_idx = start_idx

        while end_idx < n_sentences:
            candidate_parts = chunk_parts + [sentences[end_idx][1]]
            candidate_text = " ".join(candidate_parts).strip()
            if chunk_parts and len(candidate_text) > window_chars * 1.1:
                break
            chunk_parts = candidate_parts
            end_idx += 1
            if len(candidate_text) >= window_chars:
                break

        chunk_text = " ".join(chunk_parts).strip()
        if not chunk_text:
            start_idx += 1
            continue

        last_sentence_offset = sentences[end_idx - 1][0]
        end_offset = last_sentence_offset + len(sentences[end_idx - 1][1])
        yield ChunkWindow(start=start_offset, end=end_offset, text=chunk_text)

        if end_idx >= n_sentences:
            break

        stride_target = start_offset + stride_chars
        while start_idx < n_sentences and sentences[start_idx][0] < stride_target:
            start_idx += 1

        if start_idx == end_idx:
            start_idx += 1


def iter_microchunks(
    section_text: str,
    *,
    window_chars: int = 450,
    stride_chars: int = 80,
) -> Iterator[Tuple[int, int, str]]:
    """Public helper returning primitive tuples for compatibility layers."""

    for window in microchunk(section_text, window_chars=window_chars, stride_chars=stride_chars):
        yield window.start, window.end, window.text


__all__ = ["ChunkWindow", "iter_microchunks", "microchunk"]
