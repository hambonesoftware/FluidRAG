"""Upload service controller."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import secrets
import shutil
import tempfile
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Mapping

from pydantic import BaseModel

from ...adapters.storage import StorageAdapter
from ...config import get_settings
from ...util.audit import stage_record
from ...util.errors import AppError, NotFoundError, ValidationError
from ...util.logging import get_logger, log_span
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
    source_path: str


def ensure_normalized(
    file_id: str | None = None,
    file_name: str | None = None,
    *,
    upload_bytes: bytes | None = None,
    upload_filename: str | None = None,
) -> NormalizedDocInternal:
    """Controller: orchestrates validators, pdf normalize, OCR, manifest & DB."""
    storage = StorageAdapter()
    try:
        validate_upload_inputs(
            file_id=file_id,
            file_name=file_name,
            upload_bytes=upload_bytes,
            upload_filename=upload_filename,
        )
        seed_filename = upload_filename or file_name
        doc_id = make_doc_id(file_id=file_id, file_name=seed_filename)

        if upload_bytes is not None:
            source_bytes = upload_bytes
            original_source_path = None
        else:
            source_bytes, original_source_path = _resolve_source_payload(
                file_id=file_id, file_name=file_name
            )
        source_storage_path = storage.save_source_pdf(
            doc_id=doc_id, filename=seed_filename, payload=source_bytes
        )
        source_checksum = hashlib.sha256(source_bytes).hexdigest()

        logger.info("upload.ensure_normalized.start", extra={"doc_id": doc_id})
        normalized = normalize_pdf(
            doc_id=doc_id,
            file_id=file_id,
            file_name=seed_filename,
            source_bytes=source_bytes,
        )
        normalized = try_ocr_if_needed(normalized)
        normalized.setdefault("audit", []).append(
            stage_record(stage="normalize.persist", status="ok", doc_id=doc_id)
        )

        source_meta = normalized.setdefault("source", {})
        if original_source_path is not None:
            source_meta["resolved_path"] = str(original_source_path)
        source_meta["stored_path"] = str(source_storage_path)
        source_meta["checksum"] = source_checksum
        source_meta["bytes"] = len(source_bytes)
        normalized.setdefault("stats", {})["source_bytes"] = len(source_bytes)

        normalized_path = storage.save_json(
            doc_id=doc_id, name="normalize.json", payload=normalized
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
            source_path=str(source_storage_path),
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


class UploadProcessingError(ValidationError):
    """Error raised during direct upload processing with rich metadata."""

    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class UploadRecord(BaseModel):
    """Stored upload metadata record."""

    doc_id: str
    filename_original: str
    filename_stored: str
    size_bytes: int
    sha256: str
    doc_label: str | None = None
    project_id: str | None = None
    uploaded_at: datetime
    updated_at: datetime
    storage_path: str
    request_id: str | None = None
    job_id: str | None = None
    status: str = "uploaded"
    artifacts: dict[str, Any] = {}
    error: dict[str, Any] | None = None


class UploadResponseModel(BaseModel):
    """Response returned to API consumers for direct uploads."""

    doc_id: str
    filename: str
    size_bytes: int
    sha256: str
    stored_path: str
    job_id: str | None = None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        logger.warning(
            "upload.index.decode_error", extra={"path": str(path), "error": str(exc)}
        )
        return {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _flatten_app_path(path_str: str) -> Path:
    base = Path(__file__).resolve().parents[4]
    path = Path(path_str)
    if not path.is_absolute():
        path = (base / path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _detect_mime(path: Path) -> str:
    try:
        import magic  # type: ignore[import-not-found]

        with contextlib.suppress(Exception):
            detected = magic.from_file(str(path), mime=True)
            if isinstance(detected, str):
                return detected
    except Exception:  # pragma: no cover - optional dependency
        logger.debug("upload.mime.magic_unavailable")

    # Fallback: inspect first bytes for PDF signature
    signature = path.read_bytes()[:5]
    if signature.startswith(b"%PDF-"):
        return "application/pdf"
    raise UploadProcessingError(
        code="unsupported_mime",
        status_code=415,
        message="File MIME type is not supported.",
    )


def _enforce_double_extension_guard(filename: str, allowed: set[str]) -> None:
    name = filename.lower()
    for ext in allowed:
        if name.endswith(ext):
            base = name[: -len(ext)]
            for other_ext in allowed:
                if other_ext != ext and base.endswith(other_ext):
                    raise UploadProcessingError(
                        code="unsupported_extension",
                        status_code=400,
                        message="File extension is not allowed.",
                    )
            # Guard common attack pattern like .pdf.exe
            if base.endswith(".exe") or base.endswith(".bat") or base.endswith(".com"):
                raise UploadProcessingError(
                    code="unsupported_extension",
                    status_code=400,
                    message="File extension is not allowed.",
                )


def _slugify_filename(filename: str, *, max_length: int = 180) -> str:
    normalized = unicodedata.normalize("NFKC", filename)
    normalized = normalized.strip().replace("\u200b", "")
    safe_chars = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized)
    safe_chars = re.sub(r"-+", "-", safe_chars).strip("-._")
    if not safe_chars:
        safe_chars = "document"
    if len(safe_chars) > max_length:
        base, ext = os.path.splitext(safe_chars)
        space = max_length - len(ext)
        safe_chars = f"{base[:space].rstrip('-_.')}" + ext
    return safe_chars or "document.pdf"


def _ulid() -> str:
    timestamp_ms = int(time.time() * 1000)
    random_bits = secrets.randbits(80)
    value = (timestamp_ms << 80) | random_bits
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    chars = []
    for _ in range(26):
        value, idx = divmod(value, 32)
        chars.append(alphabet[idx])
    encoded = "".join(reversed(chars))
    return f"doc_{encoded}"


class UploadIndex:
    """Checksum-based dedupe index stored on disk."""

    def __init__(self, final_dir: Path) -> None:
        self.final_dir = final_dir
        self.path = final_dir / "_index.json"
        self._data = _load_json(self.path)

    def find(self, sha256: str) -> dict[str, Any] | None:
        entry = self._data.get(sha256)
        if not isinstance(entry, dict):
            return None
        return entry

    def record(self, sha256: str, payload: Mapping[str, Any]) -> None:
        self._data[sha256] = dict(payload)
        _write_json(self.path, self._data)


def _stream_to_temp(
    stream: BinaryIO,
    *,
    max_bytes: int,
    temp_dir: Path,
) -> tuple[Path, int, str]:
    hasher = hashlib.sha256()
    size = 0
    temp_dir.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=temp_dir, suffix=".upload")
    tmp_file_path = Path(tmp_path)
    os.close(tmp_fd)
    try:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise UploadProcessingError(
                    code="file_too_large",
                    status_code=413,
                    message="Uploaded file exceeds maximum size.",
                )
            hasher.update(chunk)
            with tmp_file_path.open("ab") as handle:
                handle.write(chunk)
    except UploadProcessingError:
        tmp_file_path.unlink(missing_ok=True)
        raise
    sha256 = hasher.hexdigest()
    if size == 0:
        tmp_file_path.unlink(missing_ok=True)
        raise UploadProcessingError(
            code="checksum_failed",
            status_code=500,
            message="Failed to compute checksum for uploaded file.",
        )
    return tmp_file_path, size, sha256


def _load_record(doc_dir: Path) -> UploadRecord | None:
    record_path = doc_dir / "index.json"
    if not record_path.exists():
        return None
    payload = _load_json(record_path)
    try:
        return UploadRecord(**payload)
    except Exception:  # pragma: no cover - corrupt index
        logger.warning("upload.record.invalid", extra={"path": str(record_path)})
        return None


def _persist_record(doc_dir: Path, record: UploadRecord) -> None:
    record_path = doc_dir / "index.json"
    _write_json(record_path, record.model_dump())


def _run_parser_pipeline(
    *,
    doc_dir: Path,
    doc_id: str,
    sha256: str,
    request_id: str | None,
) -> dict[str, Any]:
    parser_dir = doc_dir / "parser"
    parser_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    node_id = f"header:{uuid.uuid4().hex[:16]}"
    headers_tree = {
        "doc_id": doc_id,
        "generated_at": now,
        "source_sha256": sha256,
        "tuning_profile": None,
        "nodes": [
            {
                "id": node_id,
                "parent_id": None,
                "level": 1,
                "text_raw": "Document",
                "text_norm": "document",
                "page_range": {"start": 1, "end": 1},
                "spans": [],
                "scores": {
                    "regex": 0.0,
                    "style": 0.0,
                    "entropy": 0.0,
                    "graph": 0.0,
                    "fluid": 0.0,
                    "llm_vote": 0.0,
                    "total": 0.0,
                },
                "decision": "promote.header",
                "stitch": {"joined": False},
            }
        ],
        "artifacts": {
            "gaps_path": str(parser_dir / "gaps.json"),
            "audit_html": str(parser_dir / "audit.html"),
            "audit_md": str(parser_dir / "audit.md"),
            "results_junit": str(parser_dir / "results.junit.xml"),
        },
    }
    _write_json(parser_dir / "headers.json", headers_tree)
    _write_json(
        parser_dir / "gaps.json",
        {
            "schemas": ["numeric", "appendix", "letter_numeric"],
            "holes_filled": [],
            "generated_at": now,
        },
    )
    for name, content in {
        "audit.html": "<html><body><h1>Parser Audit</h1></body></html>",
        "audit.md": "# Parser Audit\n\nMinimal stub report.",
        "results.junit.xml": "<testsuite name=\"parser\"></testsuite>",
    }.items():
        target = parser_dir / name
        target.write_text(content, encoding="utf-8")
    logger.debug(
        "upload.parser_pipeline.stub_completed",
        extra={"doc_id": doc_id, "request_id": request_id},
    )
    return headers_tree


def process_upload(
    *,
    stream: BinaryIO,
    filename: str,
    doc_label: str | None,
    project_id: str | None,
    request_id: str | None,
    client_ip: str | None,
) -> tuple[UploadResponseModel, bool]:
    """Process direct uploads with validation, dedupe, and pipeline kick-off."""

    settings = get_settings()
    allowed_ext = {
        ext if ext.startswith(".") else f".{ext}"
        for ext in settings.upload_allowed_ext
    }
    max_bytes = int(settings.upload_max_mb * 1024 * 1024)
    temp_dir = _flatten_app_path(settings.upload_storage_temp)
    final_dir = _flatten_app_path(settings.upload_storage_final)
    filename = filename.strip() or "document.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_ext:
        raise UploadProcessingError(
            code="unsupported_extension",
            status_code=400,
            message="File extension is not allowed.",
        )
    _enforce_double_extension_guard(filename, allowed_ext)

    with log_span(
        "upload.process_upload",
        logger=logger,
        extra={
            "request_id": request_id,
            "filename": filename,
            "client_ip": client_ip,
        },
    ) as span_meta:
        tmp_path, size_bytes, sha256 = _stream_to_temp(
            stream, max_bytes=max_bytes, temp_dir=temp_dir
        )
        span_meta["size_bytes"] = size_bytes
        mime = _detect_mime(tmp_path)
        span_meta["mime"] = mime
        allowed_mime = {m.lower() for m in settings.upload_allowed_mime}
        if mime.lower() not in allowed_mime:
            tmp_path.unlink(missing_ok=True)
            raise UploadProcessingError(
                code="unsupported_mime",
                status_code=415,
                message="File MIME type is not supported.",
            )

        index = UploadIndex(final_dir)
        existing = index.find(sha256)
        if existing:
            existing_size = int(existing.get("size_bytes", 0))
            if existing_size != size_bytes:
                tmp_path.unlink(missing_ok=True)
                raise UploadProcessingError(
                    code="checksum_collision",
                    status_code=409,
                    message="Checksum collision detected with mismatched metadata.",
                )
            doc_id = str(existing.get("doc_id"))
            logger.info(
                "upload.duplicate_document",
                extra={
                    "doc_id": doc_id,
                    "request_id": request_id,
                    "sha256": sha256,
                    "size_bytes": size_bytes,
                },
            )
            tmp_path.unlink(missing_ok=True)
            record = _load_record(final_dir / doc_id)
            if record is None:
                raise UploadProcessingError(
                    code="storage_failure",
                    status_code=500,
                    message="Server failed to persist uploaded file.",
                )
            record.updated_at = datetime.now(timezone.utc)
            _persist_record(final_dir / doc_id, record)
            return UploadResponseModel(
                doc_id=record.doc_id,
                filename=record.filename_stored,
                size_bytes=record.size_bytes,
                sha256=record.sha256,
                stored_path=record.storage_path,
                job_id=record.job_id,
            ), True

        doc_id = _ulid()
        safe_name = _slugify_filename(filename)
        doc_dir = final_dir / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        stored_path = doc_dir / safe_name
        try:
            shutil.move(str(tmp_path), stored_path)
        except Exception as exc:  # pragma: no cover - IO failure
            tmp_path.unlink(missing_ok=True)
            raise UploadProcessingError(
                code="storage_failure",
                status_code=500,
                message="Server failed to persist uploaded file.",
            ) from exc

        uploaded_at = datetime.now(timezone.utc)
        record = UploadRecord(
            doc_id=doc_id,
            filename_original=filename,
            filename_stored=safe_name,
            size_bytes=size_bytes,
            sha256=sha256,
            doc_label=doc_label,
            project_id=project_id,
            uploaded_at=uploaded_at,
            updated_at=uploaded_at,
            storage_path=str(stored_path),
            request_id=request_id,
            status="uploaded",
            artifacts={},
        )
        _persist_record(doc_dir, record)
        index.record(
            sha256,
            {
                "doc_id": doc_id,
                "size_bytes": size_bytes,
                "stored_path": str(stored_path),
                "filename": safe_name,
            },
        )

        headers_tree = _run_parser_pipeline(
            doc_dir=doc_dir, doc_id=doc_id, sha256=sha256, request_id=request_id
        )
        artifacts = {
            "base_dir": str(doc_dir / "parser"),
            "detected_headers": str(doc_dir / "parser" / "headers.json"),
            "gaps": str(doc_dir / "parser" / "gaps.json"),
            "audit_html": str(doc_dir / "parser" / "audit.html"),
            "audit_md": str(doc_dir / "parser" / "audit.md"),
            "results_junit": str(doc_dir / "parser" / "results.junit.xml"),
        }
        record.status = "completed"
        record.updated_at = datetime.now(timezone.utc)
        record.artifacts = artifacts
        record.job_id = uuid.uuid4().hex
        _persist_record(doc_dir, record)

        logger.info(
            "upload.process_upload.success",
            extra={
                "doc_id": doc_id,
                "request_id": request_id,
                "sha256": sha256,
                "size_bytes": size_bytes,
                "job_id": record.job_id,
            },
        )
        return UploadResponseModel(
            doc_id=doc_id,
            filename=safe_name,
            size_bytes=size_bytes,
            sha256=sha256,
            stored_path=str(stored_path),
            job_id=record.job_id,
        ), False


def get_status(doc_id: str) -> UploadRecord:
    """Fetch stored metadata for a document."""

    settings = get_settings()
    final_dir = _flatten_app_path(settings.upload_storage_final)
    doc_dir = final_dir / doc_id
    record = _load_record(doc_dir)
    if record is None:
        raise NotFoundError(f"document not found: {doc_id}")
    return record


def get_headers(doc_id: str) -> dict[str, Any]:
    """Load headers tree artifact for a document."""

    record = get_status(doc_id)
    headers_path = Path(record.artifacts.get("detected_headers", ""))
    if not headers_path.exists():
        raise NotFoundError(f"headers not available for document: {doc_id}")
    return _load_json(headers_path)
