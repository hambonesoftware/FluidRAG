"""Filesystem helpers for uploaded file persistence."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2
from tempfile import NamedTemporaryFile
from typing import Iterable

from .....config import get_settings
from .....util.errors import ValidationError
from .....util.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class StoredUpload:
    """Descriptor for a file persisted to the quarantine directory."""

    path: str
    original_filename: str
    size_bytes: int
    sha256: str
    content_type: str | None = None


def _quarantine_root() -> Path:
    settings = get_settings()
    root = Path(settings.artifact_root_path) / "quarantine"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _random_suffix() -> str:
    return secrets.token_hex(8)


async def persist_upload_file(
    upload_file: "UploadFile", *, max_bytes: int | None = None
) -> StoredUpload:  # pragma: no cover - exercised via FastAPI tests
    """Persist an inbound ``UploadFile`` to disk and compute checksum."""

    try:
        from fastapi import UploadFile
    except Exception as exc:  # pragma: no cover - defensive import guard
        raise RuntimeError("FastAPI UploadFile unavailable") from exc

    if not isinstance(upload_file, UploadFile):  # pragma: no cover - guardrail
        raise TypeError("persist_upload_file expects a FastAPI UploadFile")

    settings = get_settings()
    chunk_size = settings.storage_chunk_bytes()
    quarantine = _quarantine_root()
    original_name = upload_file.filename or f"upload-{_random_suffix()}"
    suffix = Path(original_name).suffix or ".bin"

    hasher = hashlib.sha256()
    size_bytes = 0
    with NamedTemporaryFile(
        mode="wb", suffix=suffix, dir=quarantine, delete=False
    ) as handle:
        while True:
            chunk = await upload_file.read(chunk_size)
            if not chunk:
                break
            size_bytes += len(chunk)
            if max_bytes is not None and size_bytes > max_bytes:
                handle.close()
                Path(handle.name).unlink(missing_ok=True)
                raise ValidationError("uploaded file exceeds configured size limit")
            hasher.update(chunk)
            handle.write(chunk)
        stored_path = handle.name

    sha256 = hasher.hexdigest()
    logger.info(
        "upload.persist_upload_file",
        extra={
            "path": stored_path,
            "size_bytes": size_bytes,
            "sha256": sha256,
            "content_type": upload_file.content_type,
        },
    )
    # Reset the upload file pointer so downstream consumers can re-read if needed
    await upload_file.seek(0)
    return StoredUpload(
        path=stored_path,
        original_filename=original_name,
        size_bytes=size_bytes,
        sha256=sha256,
        content_type=upload_file.content_type,
    )


def compute_sha256(path: str | Path) -> str:
    """Compute the SHA-256 hash for a local file path."""

    target = Path(path)
    hasher = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def copy_into_doc_dir(source: Path, destination_dir: Path, name_candidates: Iterable[str]) -> Path:
    """Copy or move a source file into the document directory."""

    destination_dir.mkdir(parents=True, exist_ok=True)
    clean_names = [candidate for candidate in name_candidates if candidate]
    filename = clean_names[0] if clean_names else f"upload-{_random_suffix()}{source.suffix}"
    safe_name = Path(filename).name
    destination = destination_dir / safe_name
    if destination.exists():
        if "quarantine" in source.parts:
            source.unlink(missing_ok=True)
        return destination
    if source.is_file():
        copy2(source, destination)
        if "quarantine" in source.parts:
            source.unlink(missing_ok=True)
    else:
        destination.write_bytes(b"")
    return destination


__all__ = [
    "StoredUpload",
    "persist_upload_file",
    "compute_sha256",
    "copy_into_doc_dir",
]
