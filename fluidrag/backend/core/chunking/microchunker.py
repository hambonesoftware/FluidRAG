"""Micro-chunk generation utilities."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterator, List, Tuple


@dataclass
class Chunk:
    """Metadata describing a micro-chunk emitted by :func:`chunk`."""

    start: int
    end: int
    text: str
    window_chars: int
    stride_chars: int
    E: float
    F: float
    H: float


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


def _compute_signals(text: str) -> Tuple[float, float, float]:
    """Compute doc-invariant entropy/flow/heuristic signals for ``text``."""

    tokens = re.findall(r"\w+", text)
    total = len(tokens) or 1
    numeric_tokens = len(re.findall(r"\d+(?:\.\d+)?", text))
    unit_tokens = len(
        re.findall(
            r"(mm|cm|m|in|ft|psi|bar|kPa|MPa|A|mA|kA|V|VAC|VDC|kV|kW|kVA|°C|°F|Hz|rpm|N|kN|lbf)",
            text,
        )
    )
    inequality_count = len(re.findall(r"(≥|<=|≤|>=|=|==|>|<|±)", text))
    directive_hits = sum(text.lower().count(token) for token in ("shall", "must", "ensure", "provide"))

    entropy_signal = min(1.0, (numeric_tokens / total) + 0.3 * unit_tokens)
    flow_signal = min(1.0, 0.3 + 0.1 * directive_hits)
    hep_signal = 1.0 / (1.0 + math.exp(-0.6 * (directive_hits + inequality_count + unit_tokens)))

    filler = text.lower().count("lorem")
    hep_signal = max(0.0, min(1.0, hep_signal - 0.05 * filler))

    return round(entropy_signal, 4), round(flow_signal, 4), round(hep_signal, 4)


def chunk(
    section_text: str,
    *,
    window_chars: int = 450,
    stride_chars: int = 80,
) -> Iterator[Chunk]:
    """Yield overlapping window chunks for ``section_text`` with E/F/H signals."""

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
        entropy, flow, hep = _compute_signals(chunk_text)
        yield Chunk(
            start=start_offset,
            end=end_offset,
            text=chunk_text,
            window_chars=window_chars,
            stride_chars=stride_chars,
            E=entropy,
            F=flow,
            H=hep,
        )

        if end_idx >= n_sentences:
            break

        stride_target = start_offset + stride_chars
        while start_idx < n_sentences and sentences[start_idx][0] < stride_target:
            start_idx += 1

        if start_idx == end_idx:
            start_idx += 1


def microchunk(
    section_text: str,
    *,
    window_chars: int = 450,
    stride_chars: int = 80,
) -> Iterator[Chunk]:
    """Backward-compatible alias for :func:`chunk`."""

    yield from chunk(section_text, window_chars=window_chars, stride_chars=stride_chars)


def iter_microchunks(
    section_text: str,
    *,
    window_chars: int = 450,
    stride_chars: int = 80,
) -> Iterator[Tuple[int, int, str]]:
    """Public helper returning primitive tuples for compatibility layers."""

    for window in microchunk(section_text, window_chars=window_chars, stride_chars=stride_chars):
        yield window.start, window.end, window.text


__all__ = ["Chunk", "chunk", "iter_microchunks", "microchunk"]
