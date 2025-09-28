"""Header controller."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List

from backend.app.adapters import storage
from backend.app.contracts.headers import Header, HeaderChunk
from backend.app.util.errors import AppError
from backend.app.util.logging import get_logger

from .packages.heur.regex_bank import header_patterns
from .packages.join.stitcher import stitch_headers
from .packages.rechunk.by_headers import rechunk_by_headers
from .packages.repair.sequence import repair_sequence
from .packages.score.typo_features import score_chunk

logger = get_logger(__name__)

_STOPWORDS = {"the", "and", "with", "for", "from", "into", "onto", "using"}


@dataclass
class HeaderJoinInternal:
    """Internal header join result."""

    doc_id: str
    headers_path: str
    header_chunks_path: str
    headers: List[Header]
    header_chunks: List[HeaderChunk]


def handle_header_errors(e: Exception) -> None:
    """Normalize and raise header errors."""

    if isinstance(e, AppError):
        raise
    logger.exception("header_error", exc_info=e)
    raise AppError("Header detection failed") from e


def _clean_token(token: str) -> str:
    return token.strip(".,:;()[]{}")


def _sentence_candidates(text: str) -> List[List[str]]:
    segments = re.split(r"(?<=\.)\s+|\n+", text)
    words: List[List[str]] = []
    for segment in segments:
        tokens = [_clean_token(tok) for tok in segment.strip().split() if tok.strip()]
        if tokens:
            words.append(tokens)
    return words


def _extract_candidates(doc_id: str, record: Dict[str, str], index_offset: int) -> List[Dict[str, object]]:
    candidates: List[Dict[str, object]] = []
    page = record.get("page", 1)
    chunk_id = record.get("chunk_id", f"{doc_id}-chunk")
    for tokens in _sentence_candidates(record.get("text", "")):
        if not tokens:
            continue
        first = tokens[0]
        header_words: List[str] = []
        level = 1
        if first.isupper() and len(first) >= 4:
            header_words = [first.title()]
        elif first.replace(".", "").isdigit() and len(tokens) > 1:
            header_words.append(first)
            extras = 0
            for token in tokens[1:]:
                clean = token
                if not clean:
                    break
                if clean.lower() in _STOPWORDS:
                    break
                if not clean[0].isupper():
                    break
                header_words.append(clean)
                extras += 1
                if extras >= 2:
                    break
            if len(header_words) <= 1:
                continue
            level = first.count(".") + 1 if "." in first else 1
        else:
            continue

        header_text = " ".join(header_words)
        header_id = f"{doc_id}-header-{index_offset + len(candidates)}"
        temp_chunk = HeaderChunk(
            header_id=header_id,
            chunk_id=chunk_id,
            text=header_text,
            page=page,
        )
        confidence = score_chunk(temp_chunk)
        candidates.append(
            {
                "header_id": header_id,
                "text": header_text,
                "level": level,
                "page": page,
                "confidence": confidence,
            }
        )
    return candidates


def join_and_rechunk(doc_id: str, chunks_artifact: str) -> HeaderJoinInternal:
    """Controller: regex/typo scoring, stitching, repair, emit headers & rechunk."""

    try:
        chunk_records = storage.read_jsonl(chunks_artifact)
        patterns = header_patterns()
        candidates: List[Dict[str, object]] = []
        for record in chunk_records:
            text = record.get("text", "")
            if any(pattern.search(text) for pattern in patterns):
                candidates.extend(_extract_candidates(doc_id, record, len(candidates)))
        stitched = stitch_headers(candidates)
        repaired = repair_sequence(stitched)
        headers = [Header(**header) for header in repaired]
        headers_path = f"{doc_id}/headers/headers.json"
        storage.write_json(headers_path, [header.to_dict() for header in headers])
        header_chunks = [
            HeaderChunk(**chunk)
            for chunk in rechunk_by_headers(chunks_artifact, [header.to_dict() for header in headers])
        ]
        header_chunks_path = f"{doc_id}/headers/header_chunks.jsonl"
        storage.write_jsonl(header_chunks_path, [chunk.to_dict() for chunk in header_chunks])
        return HeaderJoinInternal(
            doc_id=doc_id,
            headers_path=headers_path,
            header_chunks_path=header_chunks_path,
            headers=headers,
            header_chunks=header_chunks,
        )
    except Exception as exc:
        handle_header_errors(exc)
        raise
