"""Simple heuristics to detect headers and map chunks to sections."""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Dict, List

from backend.app.adapters.storage import storage
from backend.app.contracts.chunking import Chunk
from backend.app.contracts.headers import Header, HeaderChunk
from backend.app.util.errors import AppError
from backend.app.util.logging import get_logger

logger = get_logger(__name__)

_HEADER_LINE = re.compile(r"^(?:(\d+(?:\.\d+)*)\s+)?(.+)$")


@dataclass(slots=True)
class HeaderJoinInternal:
    doc_id: str
    headers_path: str
    header_chunks_path: str
    headers: List[Header]
    header_chunks: List[HeaderChunk]
    sections: Dict[str, List[str]]


def handle_header_errors(error: Exception) -> None:
    if isinstance(error, AppError):
        raise
    logger.exception("header_error", exc_info=error)
    raise AppError("Header detection failed") from error


def _is_header_candidate(line: str) -> bool:
    if not line:
        return False
    if line.isupper() and len(line) >= 4:
        return True
    match = _HEADER_LINE.match(line)
    if not match:
        return False
    prefix, remainder = match.groups()
    if prefix and remainder and remainder.strip() and remainder.strip()[0].isupper():
        return True
    words = line.split()
    capitalised = sum(1 for word in words if word[:1].isupper())
    return capitalised >= max(1, len(words) // 2)


def _infer_level(line: str) -> int:
    match = _HEADER_LINE.match(line)
    if match and match.group(1):
        return max(1, match.group(1).count(".") + 1)
    return 1


def _load_chunks(chunks_artifact: str) -> List[Chunk]:
    payloads = storage.read_jsonl(chunks_artifact)
    return [Chunk(**record) for record in payloads]


def _build_header_chunks(doc_id: str, headers: List[Header], chunk_lookup: Dict[str, Chunk]) -> List[HeaderChunk]:
    header_chunks: List[HeaderChunk] = []
    for index, header in enumerate(headers):
        chunk = chunk_lookup.get(header.start_chunk)
        text = chunk.text if chunk else header.title
        header_chunks.append(
            HeaderChunk(
                header_id=f"{doc_id}-header-{index}",
                chunk_id=header.start_chunk,
                text=text,
                page=1,
            )
        )
    return header_chunks


def _build_sections(headers: List[Header], chunks: List[Chunk]) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = {"Document": []}
    current = "Document"
    header_map = {header.start_chunk: header.title for header in headers}
    for chunk in sorted(chunks, key=lambda item: item.start):
        maybe_header = header_map.get(chunk.chunk_id)
        if maybe_header:
            current = maybe_header
            sections.setdefault(current, [])
        sections.setdefault(current, []).append(chunk.chunk_id)
    return sections


def join_and_rechunk(doc_id: str, chunks_artifact: str) -> HeaderJoinInternal:
    try:
        chunks = _load_chunks(chunks_artifact)
        chunk_lookup = {chunk.chunk_id: chunk for chunk in chunks}
        headers: List[Header] = []
        for chunk in chunks:
            line = chunk.text.strip().splitlines()[0] if chunk.text.strip() else ""
            if not _is_header_candidate(line):
                continue
            level = _infer_level(line)
            headers.append(
                Header(
                    title=line.strip(),
                    level=level,
                    start_chunk=chunk.chunk_id,
                    end_chunk=chunk.chunk_id,
                    confidence=1.0,
                )
            )

        sections = _build_sections(headers, chunks)
        header_chunks = _build_header_chunks(doc_id, headers, chunk_lookup)

        headers_payload = {
            "doc_id": doc_id,
            "headers": [asdict(header) for header in headers],
            "sections": sections,
        }
        headers_path = f"{doc_id}/headers/headers.json"
        storage.write_json(headers_path, headers_payload)

        header_chunks_path = f"{doc_id}/headers/header_chunks.jsonl"
        storage.write_jsonl(header_chunks_path, [asdict(chunk) for chunk in header_chunks])

        return HeaderJoinInternal(
            doc_id=doc_id,
            headers_path=headers_path,
            header_chunks_path=header_chunks_path,
            headers=headers,
            header_chunks=header_chunks,
            sections=sections,
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        handle_header_errors(exc)
        raise
