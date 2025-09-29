"""Sentence segmentation utilities for UF chunking."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .....util.logging import get_logger

logger = get_logger(__name__)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def _iter_block_text(payload: Mapping[str, Any]) -> Iterable[str]:
    blocks = payload.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, Mapping):
                text = str(block.get("text", ""))
            else:
                text = ""
            if text:
                yield text
    pages = payload.get("pages")
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, Mapping):
                continue
            nested = page.get("blocks", [])
            if not isinstance(nested, list):
                continue
            for block in nested:
                if isinstance(block, Mapping):
                    text = str(block.get("text", ""))
                else:
                    text = ""
                if text:
                    yield text


def split_sentences(normalize_artifact_path: str | None = None) -> list[str]:
    """Segment text into sentences using punctuation and layout."""
    if not normalize_artifact_path:
        return []
    path = Path(normalize_artifact_path)
    if not path.exists():
        logger.warning(
            "chunk.sentences.missing_artifact", extra={"path": normalize_artifact_path}
        )
        raise FileNotFoundError(normalize_artifact_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error(
            "chunk.sentences.invalid_json",
            extra={"path": normalize_artifact_path, "error": str(exc)},
        )
        raise

    sentences: list[str] = []
    for block_text in _iter_block_text(payload):
        candidates = _SENTENCE_SPLIT.split(block_text.strip())
        for candidate in candidates:
            cleaned = candidate.strip()
            if cleaned:
                sentences.append(cleaned)
    return sentences
