"""Upload service controller."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from ...config import get_settings
from ...util.audit import stage_record
from ...util.errors import AppError, NotFoundError, ValidationError
from ...util.logging import get_logger
from .packages.emit.manifest import write_manifest
from .packages.guards.validators import validate_upload_inputs
from .packages.normalize.ocr import try_ocr_if_needed
from .packages.normalize.pdf_reader import normalize_pdf

logger = get_logger(__name__)


class NormalizedDocInternal(BaseModel):
    """Internal normalized result."""

    doc_id: str
    normalized_path: str
    manifest_path: str
    avg_coverage: float
    block_count: int
    ocr_performed: bool
    source_checksum: str
    source_bytes: int


def ensure_normalized(
    file_id: str | None = None, file_name: str | None = None
) -> NormalizedDocInternal:
    """Controller: orchestrates validators, pdf normalize, OCR, manifest & DB."""
    settings = get_settings()
    try:
        validate_upload_inputs(file_id=file_id, file_name=file_name)
        doc_id = make_doc_id(file_id=file_id, file_name=file_name)
        artifact_root = Path(settings.artifact_root_path)
        artifact_root.mkdir(parents=True, exist_ok=True)
        doc_dir = artifact_root / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)

        source_bytes, source_path = _resolve_source_payload(
            file_id=file_id, file_name=file_name
        )
        source_checksum = hashlib.sha256(source_bytes).hexdigest()

        logger.info("upload.ensure_normalized.start", extra={"doc_id": doc_id})
        normalized = normalize_pdf(
            doc_id=doc_id,
            file_id=file_id,
            file_name=file_name,
            source_bytes=source_bytes,
        )
        normalized = try_ocr_if_needed(normalized)
        normalized.setdefault("audit", []).append(
            stage_record(stage="normalize.persist", status="ok", doc_id=doc_id)
        )

        source_meta = normalized.setdefault("source", {})
        if source_path is not None:
            source_meta["resolved_path"] = str(source_path)
        source_meta["checksum"] = source_checksum
        source_meta["bytes"] = len(source_bytes)
        normalized.setdefault("stats", {})["source_bytes"] = len(source_bytes)

        normalized_path = doc_dir / "normalize.json"
        normalized_path.write_text(
            json.dumps(normalized, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        manifest = write_manifest(
            doc_id=doc_id,
            artifact_path=str(normalized_path),
            kind="normalize",
            extra={
                "source_checksum": source_checksum,
                "source_bytes": len(source_bytes),
            },
        )
        logger.info(
            "upload.ensure_normalized.success",
            extra={
                "doc_id": doc_id,
                "path": str(normalized_path),
                "avg_coverage": normalized["stats"].get("avg_coverage", 0.0),
                "block_count": normalized["stats"].get("block_count", 0),
                "ocr_performed": normalized["stats"].get("ocr_performed", False),
                "source_checksum": source_checksum,
                "source_bytes": len(source_bytes),
            },
        )
        return NormalizedDocInternal(
            doc_id=doc_id,
            normalized_path=str(normalized_path),
            manifest_path=manifest["manifest_path"],
            avg_coverage=float(normalized["stats"].get("avg_coverage", 0.0)),
            block_count=int(normalized["stats"].get("block_count", 0)),
            ocr_performed=bool(normalized["stats"].get("ocr_performed", False)),
            source_checksum=source_checksum,
            source_bytes=len(source_bytes),
        )
    except Exception as exc:  # noqa: BLE001 - convert to domain errors
        handle_upload_errors(exc)
        raise  # pragma: no cover - handle_upload_errors will raise


def make_doc_id(file_id: str | None = None, file_name: str | None = None) -> str:
    """Generate stable doc_id from inputs/time."""
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S%f")
    seed = "|".join(filter(None, [file_id or "", file_name or ""]))
    digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
    return f"{timestamp}-{digest}"


def _resolve_source_payload(
    *, file_id: str | None, file_name: str | None
) -> tuple[bytes, Path | None]:
    """Return payload bytes and resolved path for the provided source."""
    if file_name:
        path = Path(file_name).expanduser()
        try:
            return path.read_bytes(), path.resolve()
        except OSError as exc:  # pragma: no cover - guarded by validation
            raise ValidationError(str(exc)) from exc
    if file_id:
        return file_id.encode("utf-8"), None
    return b"", None


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
