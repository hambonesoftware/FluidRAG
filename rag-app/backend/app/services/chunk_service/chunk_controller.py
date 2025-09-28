"""Chunk controller orchestrating segmentation and indexing."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from ...config import get_settings
from ...contracts.chunking import UFChunk
from ...util.audit import stage_record
from ...util.errors import AppError, NotFoundError, ValidationError
from ...util.logging import get_logger
from .packages.features.typography import extract_typography
from .packages.index.local_vss import build_local_index
from .packages.segment.sentences import split_sentences
from .packages.segment.uf_chunker import uf_chunk

logger = get_logger(__name__)


class ChunkInternal(BaseModel):
    """Internal chunk descriptor."""

    doc_id: str
    chunks_path: str
    chunk_count: int
    index_manifest_path: str | None = None


def _validate_inputs(
    doc_id: str | None, normalize_artifact: str | None
) -> tuple[str, str]:
    if not doc_id or not doc_id.strip():
        raise ValidationError("doc_id is required for chunking")
    if not normalize_artifact or not normalize_artifact.strip():
        raise ValidationError("normalize_artifact is required for chunking")
    return doc_id.strip(), normalize_artifact.strip()


def run_uf_chunking(
    doc_id: str | None = None, normalize_artifact: str | None = None
) -> ChunkInternal:
    """Controller for chunking & local index building."""
    doc_id, normalize_artifact = _validate_inputs(doc_id, normalize_artifact)
    settings = get_settings()
    artifact_root = Path(settings.artifact_root_path) / doc_id
    artifact_root.mkdir(parents=True, exist_ok=True)
    target_tokens = int(getattr(settings, "chunk_target_tokens", 90))
    overlap = int(getattr(settings, "chunk_token_overlap", 12))
    try:
        sentences = split_sentences(normalize_artifact)
        if not sentences:
            raise ValidationError("no sentences available for chunking")
        typography = extract_typography(normalize_artifact)
        chunk_dicts = uf_chunk(
            sentences=sentences,
            typography=typography,
            target_tokens=target_tokens,
            overlap=overlap,
        )
        if not chunk_dicts:
            raise AppError("failed to create chunks")
        chunks_path = artifact_root / "uf_chunks.jsonl"
        with chunks_path.open("w", encoding="utf-8") as handle:
            for index, chunk in enumerate(chunk_dicts, start=1):
                payload = UFChunk(
                    chunk_id=f"{doc_id}:c{index}",
                    doc_id=doc_id,
                    text=chunk["text"],
                    sentence_start=chunk["sentence_start"],
                    sentence_end=chunk["sentence_end"],
                    token_count=chunk["token_count"],
                    typography=chunk.get("typography", {}),
                ).model_dump()
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        build_local_index(doc_id=doc_id, chunks_path=str(chunks_path))
        manifest_path = artifact_root / "index.manifest.json"
        audit_path = artifact_root / "chunk.audit.json"
        audit_payload = stage_record(
            stage="chunk.build",
            status="ok",
            doc_id=doc_id,
            chunks=len(chunk_dicts),
            target_tokens=target_tokens,
            overlap=overlap,
        )
        audit_path.write_text(json.dumps(audit_payload, indent=2), encoding="utf-8")
        logger.info(
            "chunk.run.success",
            extra={
                "doc_id": doc_id,
                "chunks": len(chunk_dicts),
                "chunks_path": str(chunks_path),
            },
        )
        return ChunkInternal(
            doc_id=doc_id,
            chunks_path=str(chunks_path),
            chunk_count=len(chunk_dicts),
            index_manifest_path=str(manifest_path) if manifest_path.exists() else None,
        )
    except FileNotFoundError as exc:
        handle_chunk_errors(exc)
        raise
    except Exception as exc:  # noqa: BLE001
        handle_chunk_errors(exc)
        raise


def handle_chunk_errors(e: Exception) -> None:
    """Normalize and raise chunk errors."""
    if isinstance(e, ValidationError):
        logger.warning("chunk.validation_failed", extra={"error": str(e)})
        raise
    if isinstance(e, FileNotFoundError):
        logger.error("chunk.artifact_missing", extra={"error": str(e)})
        raise NotFoundError(str(e)) from e
    if isinstance(e, AppError):
        raise
    logger.error("chunk.unexpected", extra={"error": str(e), "type": type(e).__name__})
    raise AppError("chunking failed") from e


__all__ = ["run_uf_chunking", "handle_chunk_errors", "ChunkInternal"]
