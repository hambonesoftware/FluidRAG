"""Rechunk UF chunks along header boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .....util.logging import get_logger

logger = get_logger(__name__)


def _load_chunks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        logger.warning("headers.rechunk.missing_chunks", extra={"path": str(path)})
        return []
    rows: list[dict[str, Any]] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw:
                continue
            try:
                rows.append(json.loads(raw))
            except json.JSONDecodeError:
                logger.debug("headers.rechunk.invalid_row")
    except OSError as exc:
        logger.error(
            "headers.rechunk.read_failed",
            extra={"path": str(path), "error": str(exc)},
        )
    return rows


def rechunk_by_headers(
    chunks_artifact_path: str,
    headers: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Map chunks to section ranges; output section-aligned chunks."""

    headers = headers or []
    if not headers:
        return []
    path = Path(chunks_artifact_path)
    chunk_rows = _load_chunks(path)
    if not chunk_rows:
        return []
    chunk_rows.sort(
        key=lambda row: (int(row.get("sentence_start", 0)), row.get("chunk_id", ""))
    )
    headers_sorted = sorted(
        headers,
        key=lambda h: (int(h.get("sentence_start", 0)), int(h.get("chunk_index", 0))),
    )
    header_iter = iter(headers_sorted)
    current = next(header_iter, None)
    next_header = next(header_iter, None)
    assignments: dict[str, list[dict[str, Any]]] = {
        h["header_id"]: [] for h in headers_sorted
    }
    for chunk in chunk_rows:
        while next_header and int(chunk.get("sentence_start", 0)) >= int(
            next_header.get("sentence_start", 0)
        ):
            current = next_header
            next_header = next(header_iter, None)
        if not current:
            current = headers_sorted[0]
        assignments.setdefault(current["header_id"], []).append(chunk)
    aggregated: list[dict[str, Any]] = []
    for header in headers_sorted:
        assigned = assignments.get(header["header_id"], [])
        text_parts = [header.get("text", "").strip()]
        chunk_ids: list[str] = []
        for chunk in assigned:
            chunk_ids.append(str(chunk.get("chunk_id")))
            chunk_text = str(chunk.get("text", "")).strip()
            if chunk_text:
                text_parts.append(chunk_text)
        combined_text = "\n\n".join(part for part in text_parts if part)
        aggregated.append(
            {
                "section_id": header.get("section_id"),
                "header_id": header.get("header_id"),
                "doc_id": header.get("doc_id"),
                "text": combined_text,
                "chunk_ids": chunk_ids,
                "header_text": header.get("text", ""),
                "level": header.get("level", 1),
                "score": float(header.get("score", 0.0)),
                "recovered": bool(header.get("recovered", False)),
                "metadata": {
                    "sentence_start": header.get("sentence_start"),
                    "sentence_end": header.get("sentence_end"),
                },
            }
        )
    logger.debug(
        "headers.rechunk.aggregated",
        extra={"sections": len(aggregated)},
    )
    return aggregated


__all__ = ["rechunk_by_headers"]
