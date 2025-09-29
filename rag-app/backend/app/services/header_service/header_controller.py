"""Header controller orchestrating heuristics, repair, and rechunking."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ...config import get_settings
from ...contracts.headers import HeaderArtifact, HeaderChunk, SectionAssignment
from ...util.audit import stage_record
from ...util.errors import AppError, NotFoundError, ValidationError
from ...util.logging import get_logger, log_span
from .packages import (
    find_header_candidates,
    rechunk_by_headers,
    repair_sequence,
    score_typo,
    stitch_headers,
)

logger = get_logger(__name__)


class HeaderJoinInternal(BaseModel):
    """Internal header join result."""

    doc_id: str
    headers_path: str
    section_map_path: str
    header_chunks_path: str
    header_count: int
    recovered_count: int


def _validate_inputs(doc_id: str, chunks_artifact: str) -> tuple[str, Path]:
    if not doc_id or not doc_id.strip():
        raise ValidationError("doc_id is required for header detection")
    if not chunks_artifact or not chunks_artifact.strip():
        raise ValidationError("chunks_artifact is required for header detection")
    path = Path(chunks_artifact)
    if not path.exists():
        raise NotFoundError(f"chunks artifact not found: {chunks_artifact}")
    return doc_id.strip(), path


def _assign_header_ids(
    doc_id: str, headers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    assigned: list[dict[str, Any]] = []
    for index, header in enumerate(headers, start=1):
        enriched = dict(header)
        enriched["doc_id"] = doc_id
        enriched["header_id"] = f"{doc_id}:h{index}"
        enriched["section_id"] = f"{doc_id}:s{index}"
        enriched.setdefault("chunk_ids", header.get("chunk_ids", []))
        enriched.setdefault("recovered", False)
        assigned.append(enriched)
    return assigned


def _persist_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _persist_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _build_section_map(chunks: list[HeaderChunk]) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    order = 0
    for chunk in chunks:
        for chunk_id in chunk.chunk_ids:
            assignments.append(
                SectionAssignment(
                    section_id=chunk.section_id,
                    header_id=chunk.header_id,
                    chunk_id=chunk_id,
                    order=order,
                ).model_dump()
            )
            order += 1
    return assignments


def join_and_rechunk(doc_id: str, chunks_artifact: str) -> HeaderJoinInternal:
    """Controller: regex/typo scoring, stitching, repair, emit headers & rechunk."""

    doc_id, chunks_path = _validate_inputs(doc_id, chunks_artifact)
    settings = get_settings()
    artifact_root = Path(settings.artifact_root_path) / doc_id
    artifact_root.mkdir(parents=True, exist_ok=True)

    stage_start = time.perf_counter()
    try:
        with log_span(
            "headers.join_and_rechunk",
            logger=logger,
            extra={"doc_id": doc_id},
        ) as span_meta:
            candidates = find_header_candidates(str(chunks_path))
            candidates = score_typo(candidates)
            stitched = stitch_headers(candidates)
            repaired = repair_sequence(stitched)
            if not repaired:
                raise AppError("no headers detected")
            repaired.sort(
                key=lambda item: (
                    int(item.get("chunk_index", 0)),
                    int(item.get("sentence_start", 0)),
                )
            )
            assigned = _assign_header_ids(doc_id, repaired)
            header_models = [
                HeaderArtifact(
                    header_id=header["header_id"],
                    doc_id=header["doc_id"],
                    text=header.get("text", ""),
                    level=int(header.get("level", 1) or 1),
                    score=float(header.get("score", 0.0)),
                    recovered=bool(header.get("recovered", False)),
                    ordinal=header.get("ordinal"),
                    section_key=str(header.get("section_key", header["header_id"])),
                    chunk_ids=[str(cid) for cid in header.get("chunk_ids", []) if cid],
                    sentence_start=int(header.get("sentence_start", 0)),
                    sentence_end=int(header.get("sentence_end", 0)),
                )
                for header in assigned
            ]
            headers_payload = [model.model_dump() for model in header_models]
            header_chunks_raw = rechunk_by_headers(str(chunks_path), assigned)
            header_chunks = [HeaderChunk(**row) for row in header_chunks_raw]
            section_map = _build_section_map(header_chunks)

            headers_path = artifact_root / "headers.json"
            section_map_path = artifact_root / "section_map.json"
            header_chunks_path = artifact_root / "header_chunks.jsonl"
            audit_path = artifact_root / "headers.audit.json"

            _persist_json(headers_path, headers_payload)
            _persist_json(section_map_path, section_map)
            _persist_jsonl(
                header_chunks_path, [chunk.model_dump() for chunk in header_chunks]
            )
            recovered_count = sum(1 for header in header_models if header.recovered)
            duration_ms = (time.perf_counter() - stage_start) * 1000.0
            span_meta["headers"] = len(header_models)
            span_meta["recovered"] = recovered_count
            _persist_json(
                audit_path,
                stage_record(
                    stage="headers.join",
                    status="ok",
                    doc_id=doc_id,
                    headers=len(header_models),
                    recovered=recovered_count,
                    duration_ms=duration_ms,
                ),
            )

            logger.info(
                "headers.join.success",
                extra={
                    "doc_id": doc_id,
                    "headers": len(header_models),
                    "recovered": recovered_count,
                },
            )

            return HeaderJoinInternal(
                doc_id=doc_id,
                headers_path=str(headers_path),
                section_map_path=str(section_map_path),
                header_chunks_path=str(header_chunks_path),
                header_count=len(header_models),
                recovered_count=recovered_count,
            )
    except Exception as exc:  # noqa: BLE001
        handle_header_errors(exc)
        raise


def handle_header_errors(e: Exception) -> None:
    """Normalize and raise header errors."""

    if isinstance(e, ValidationError):
        logger.warning("headers.validation_failed", extra={"error": str(e)})
        raise
    if isinstance(e, NotFoundError):
        logger.error("headers.artifact_missing", extra={"error": str(e)})
        raise
    if isinstance(e, AppError):
        raise
    logger.error(
        "headers.unexpected",
        extra={"error": str(e), "type": type(e).__name__},
    )
    raise AppError("header detection failed") from e


__all__ = ["join_and_rechunk", "handle_header_errors", "HeaderJoinInternal"]
