"""Utilities for deriving multi-resolution chunks (micro/meso/macro)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple

from .headers import HeaderDetector


@dataclass
class MultiResolutionChunks:
    """Container for the three resolution levels."""

    micro: List[Dict]
    meso: List[Dict]
    macro: List[Dict]


def _sentence_split(text: str) -> List[str]:
    sentences: List[str] = []
    buffer = ""
    for token in text.split():
        if buffer:
            buffer += " "
        buffer += token
        if token.endswith(('.', '!', '?')):
            sentences.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        sentences.append(buffer.strip())
    return sentences or [text.strip()]


def _window(iterable: Sequence[str], size: int, stride: int) -> Iterable[Tuple[int, List[str]]]:
    if size <= 0:
        return []
    idx = 0
    while idx < len(iterable):
        window = list(iterable[idx : idx + size])
        if not window:
            break
        yield idx, window
        idx += stride


def _chunk_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _merge_chunk(chunks: Sequence[Dict], start: int, end: int) -> Dict:
    merged = dict(chunks[start])
    merged_text = []
    for idx in range(start, end + 1):
        merged_text.append(chunks[idx].get("text", ""))
    merged["text"] = "\n".join(filter(None, merged_text))
    merged.setdefault("meta", {}).update(
        {
            "micro_children": [chunks[idx].get("id") for idx in range(start, end + 1)],
            "meso_span": (start, end),
        }
    )
    return merged


def derive_multi_resolution(
    chunks: Sequence[Dict], *, stage_tag: str, detector: HeaderDetector | None = None
) -> MultiResolutionChunks:
    """Emit micro/meso/macro chunks while preserving anchors."""

    if detector is None:
        detector = HeaderDetector()

    detector.detect(chunks)
    for idx, chunk in enumerate(chunks):
        chunk.setdefault("meta", {})
        chunk["meta"].setdefault("stage_tag", stage_tag)
        chunk.setdefault("stage_tag", stage_tag)
        chunk.setdefault("resolution", "micro")
        chunk.setdefault("break_score", chunk.get("break_score", 0.0))

    # --- build meso segments -------------------------------------------------
    boundaries = [0] + [idx for idx, chunk in enumerate(chunks) if chunk.get("header_candidate")] + [len(chunks)]
    boundaries = sorted(set(boundaries))
    meso: List[Dict] = []
    for start, end in zip(boundaries, boundaries[1:]):
        if start == end:
            continue
        span = list(range(start, end))
        merged = _merge_chunk(chunks, span[0], span[-1])
        merged["id"] = _chunk_id("meso")
        merged["resolution"] = "meso"
        merged["stage_tag"] = stage_tag
        merged.setdefault("meta", {}).update(
            {
                "stage_tag": stage_tag,
                "micro_children": [chunks[idx].get("id") for idx in span],
                "boundary_indices": (span[0], span[-1]),
            }
        )
        meso.append(merged)

    # --- build macro segments ------------------------------------------------
    macro: List[Dict] = []
    for segment in meso:
        macro_chunk = dict(segment)
        macro_chunk["id"] = _chunk_id("macro")
        macro_chunk["resolution"] = "macro"
        macro_chunk.setdefault("meta", {}).update(
            {
                "stage_tag": stage_tag,
                "macro_sources": segment["meta"].get("micro_children", []),
            }
        )
        macro.append(macro_chunk)

    # --- micro derivation ----------------------------------------------------
    micro: List[Dict] = []
    for chunk in chunks:
        text = chunk.get("text", "")
        sentences = _sentence_split(text)
        size = 4
        stride = max(1, size // 2)
        for idx, window in _window(sentences, size, stride):
            if not window:
                continue
            piece = dict(chunk)
            piece_text = " ".join(window)
            piece["text"] = piece_text
            piece["id"] = _chunk_id("micro")
            piece["resolution"] = "micro"
            piece["stage_tag"] = stage_tag
            piece.setdefault("meta", {}).update(
                {
                    "stage_tag": stage_tag,
                    "sentence_offset": idx,
                    "meso_parent_id": None,
                }
            )
            micro.append(piece)

    # Map micro chunks back to meso parents
    for segment in meso:
        child_ids = set(segment["meta"].get("micro_children", []))
        for chunk in micro:
            if chunk.get("source_id") in child_ids or chunk.get("id") in child_ids:
                chunk["meta"]["meso_parent_id"] = segment["id"]

    return MultiResolutionChunks(micro=micro, meso=meso, macro=macro)


def link_macro_assets(meso: Sequence[Dict], assets: Sequence[Dict]) -> None:
    """Attach tables or appendix assets to their macro parents."""

    appendix_map: Dict[str, Dict] = {}
    for asset in assets:
        appendix_map[str(asset.get("section_number") or asset.get("section_name") or "")] = asset

    for segment in meso:
        section = segment.get("section_number") or segment.get("meta", {}).get("section_number")
        if not section:
            continue
        asset = appendix_map.get(str(section))
        if asset is None:
            continue
        segment.setdefault("meta", {}).setdefault("linked_assets", []).append(asset.get("id"))

