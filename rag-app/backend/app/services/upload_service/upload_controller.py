"""Upload service controller."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ...config import get_settings
from ...util.audit import stage_record
from ...util.errors import AppError, NotFoundError, ValidationError
from ...util.logging import get_logger
from .packages.emit.manifest import write_manifest
from .packages.guards.validators import (
    validate_upload_inputs,
    validate_uploaded_file,
)
from .packages.normalize.ocr import try_ocr_if_needed
from .packages.normalize.pdf_reader import normalize_pdf
from .packages.storage import StoredUpload, copy_into_doc_dir, compute_sha256

logger = get_logger(__name__)


class NormalizedDocInternal(BaseModel):
    """Internal normalized result."""

    doc_id: str
    normalized_path: str
    manifest_path: str
    avg_coverage: float
    block_count: int
    ocr_performed: bool
    sha256: str
    source_path: str
    size_bytes: int
    content_type: str | None


def ensure_normalized(
    file_id: str | None = None,
    file_name: str | None = None,
    upload: StoredUpload | None = None,
) -> NormalizedDocInternal:
    """Controller: orchestrates validators, pdf normalize, OCR, manifest & DB."""
    settings = get_settings()
    try:
        source = _resolve_source(
            file_id=file_id,
            file_name=file_name,
            upload=upload,
            settings=settings,
        )
        doc_id = make_doc_id(
            file_id=file_id,
            file_name=source["original_name"],
            checksum=source["sha256"],
        )
        artifact_root = Path(settings.artifact_root_path)
        artifact_root.mkdir(parents=True, exist_ok=True)
        doc_dir = artifact_root / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        source_path = copy_into_doc_dir(
            Path(source["path"]),
            doc_dir / "source",
            [source["original_name"], file_name],
        )

        logger.info(
            "upload.ensure_normalized.start",
            extra={
                "doc_id": doc_id,
                "source": str(source_path),
                "size_bytes": source["size_bytes"],
                "sha256": source["sha256"],
            },
        )

        normalized_path = doc_dir / "normalize.json"
        if normalized_path.exists():
            existing_payload = json.loads(
                normalized_path.read_text(encoding="utf-8")
            )
            manifest = write_manifest(
                doc_id=doc_id, artifact_path=str(normalized_path), kind="normalize"
            )
            stats = existing_payload.get("stats", {})
            logger.info(
                "upload.ensure_normalized.cache_hit",
                extra={
                    "doc_id": doc_id,
                    "path": str(normalized_path),
                    "sha256": source["sha256"],
                },
            )
            return NormalizedDocInternal(
                doc_id=doc_id,
                normalized_path=str(normalized_path),
                manifest_path=manifest["manifest_path"],
                avg_coverage=float(stats.get("avg_coverage", 0.0)),
                block_count=int(stats.get("block_count", 0)),
                ocr_performed=bool(stats.get("ocr_performed", False)),
                sha256=source["sha256"],
                source_path=str(source_path),
                size_bytes=source["size_bytes"],
                content_type=source["content_type"],
            )

        normalized = normalize_pdf(
            doc_id=doc_id,
            source_path=source_path,
            source_sha256=source["sha256"],
            original_filename=source["original_name"],
            content_type=source["content_type"],
            size_bytes=source["size_bytes"],
        )
        normalized = try_ocr_if_needed(normalized)
        normalized.setdefault("audit", []).append(
            stage_record(stage="normalize.persist", status="ok", doc_id=doc_id)
        )
        normalized_path.write_text(
            json.dumps(normalized, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        manifest = write_manifest(
            doc_id=doc_id, artifact_path=str(normalized_path), kind="normalize"
        )
        normalized_stats = normalized.get("stats", {})
        stats = {
            "avg_coverage": float(normalized_stats.get("avg_coverage", 0.0)),
            "block_count": int(normalized_stats.get("block_count", 0)),
            "ocr_performed": bool(normalized_stats.get("ocr_performed", False)),
        }
        logger.info(
            "upload.ensure_normalized.success",
            extra={
                "doc_id": doc_id,
                "path": str(normalized_path),
                "avg_coverage": stats["avg_coverage"],
                "block_count": stats["block_count"],
                "ocr_performed": stats["ocr_performed"],
                "sha256": source["sha256"],
                "size_bytes": source["size_bytes"],
            },
        )
        return NormalizedDocInternal(
            doc_id=doc_id,
            normalized_path=str(normalized_path),
            manifest_path=manifest["manifest_path"],
            avg_coverage=stats["avg_coverage"],
            block_count=stats["block_count"],
            ocr_performed=stats["ocr_performed"],
            sha256=source["sha256"],
            source_path=str(source_path),
            size_bytes=source["size_bytes"],
            content_type=source["content_type"],
        )
    except Exception as exc:  # noqa: BLE001 - convert to domain errors
        handle_upload_errors(exc)
        raise  # pragma: no cover - handle_upload_errors will raise


def make_doc_id(
    file_id: str | None = None,
    file_name: str | None = None,
    checksum: str | None = None,
) -> str:
    """Generate stable doc_id from checksum/inputs."""

    if checksum:
        prefix = _slugify(file_name or file_id or "document")
        return f"{prefix}-{checksum[:16]}"

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S%f")
    seed = "|".join(filter(None, [file_id or "", file_name or ""]))
    digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"{timestamp}-{digest}"


def handle_upload_errors(e: Exception) -> None:
    """Normalize and raise application errors for upload stage."""
    if isinstance(e, ValidationError):
        logger.warning("upload.validation_failed", extra={"error": str(e)})
        raise
    if isinstance(e, FileNotFoundError):
        logger.error("upload.file_missing", extra={"error": str(e)})
        raise NotFoundError(str(e)) from e
    if isinstance(e, AppError):
        raise
    logger.error("upload.unexpected", extra={"error": str(e), "type": type(e).__name__})
    raise AppError("upload normalization failed") from e


def _slugify(candidate: str) -> str:
    text = candidate.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "document"


def _resolve_source(
    *,
    file_id: str | None,
    file_name: str | None,
    upload: StoredUpload | None,
    settings: Any,
) -> dict[str, Any]:
    """Resolve the physical file to normalize."""

    if upload is not None:
        max_bytes = int(settings.upload_max_size_mb) * 1024 * 1024
        persisted = validate_uploaded_file(
            path=upload.path,
            original_filename=upload.original_filename,
            content_type=upload.content_type,
            allowed_extensions=settings.upload_allowed_extensions,
            allowed_mimes=settings.upload_mime_allowlist,
            max_bytes=max_bytes,
        )
        return {
            "path": upload.path,
            "original_name": upload.original_filename,
            "size_bytes": int(persisted["size_bytes"]),
            "sha256": upload.sha256,
            "content_type": persisted.get("mime") or upload.content_type,
        }

    validate_upload_inputs(file_id=file_id, file_name=file_name)
    if file_name:
        source_path = Path(file_name)
        if not source_path.exists():
            raise FileNotFoundError(file_name)
        sha256 = compute_sha256(source_path)
        guessed_type, _ = mimetypes.guess_type(source_path.name)
        allowed_extensions = list(settings.upload_allowed_extensions)
        allowed_mimes = list(settings.upload_mime_allowlist)
        suffix = source_path.suffix.lower()
        if suffix and suffix not in {ext.lower() for ext in allowed_extensions}:
            allowed_extensions.append(suffix)
        if guessed_type and guessed_type not in allowed_mimes:
            allowed_mimes.append(guessed_type)
        persisted = validate_uploaded_file(
            path=str(source_path),
            original_filename=source_path.name,
            content_type=guessed_type,
            allowed_extensions=allowed_extensions,
            allowed_mimes=allowed_mimes,
            max_bytes=int(settings.upload_max_size_mb) * 1024 * 1024,
        )
        return {
            "path": str(source_path),
            "original_name": source_path.name,
            "size_bytes": int(persisted["size_bytes"]),
            "sha256": sha256,
            "content_type": persisted.get("mime") or guessed_type,
        }

    candidate = file_id or ""
    temp_path = Path(settings.artifact_root_path) / "quarantine"
    temp_path.mkdir(parents=True, exist_ok=True)
    name = f"inline-{datetime.now(tz=timezone.utc).strftime('%Y%m%d%H%M%S%f')}.txt"
    target = temp_path / name
    target.write_text(candidate, encoding="utf-8")
    sha256 = compute_sha256(target)
    persisted = validate_uploaded_file(
        path=str(target),
        original_filename=name,
        content_type="text/plain",
        allowed_extensions=settings.upload_allowed_extensions + [".txt"],
        allowed_mimes=settings.upload_mime_allowlist + ["text/plain"],
        max_bytes=int(settings.upload_max_size_mb) * 1024 * 1024,
    )
    return {
        "path": str(target),
        "original_name": name,
        "size_bytes": int(persisted["size_bytes"]),
        "sha256": sha256,
        "content_type": persisted.get("mime") or "text/plain",
    }
