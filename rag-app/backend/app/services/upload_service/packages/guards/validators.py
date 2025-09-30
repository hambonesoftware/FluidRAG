"""Upload input validation utilities."""

from __future__ import annotations

import mimetypes
from pathlib import Path, PurePath

import filetype

from .....util.errors import ValidationError


_DOUBLE_EXTENSION_BLOCKLIST = {
    ".exe",
    ".js",
    ".msi",
    ".scr",
    ".bat",
    ".cmd",
    ".sh",
}


def validate_upload_inputs(
    file_id: str | None = None,
    file_name: str | None = None,
) -> None:
    """Raise on invalid upload inputs."""
    if not file_id and not file_name:
        raise ValidationError("either file_id or file_name must be provided")

    if file_id is not None:
        candidate = file_id.strip()
        if not candidate:
            raise ValidationError("file_id cannot be blank")
        if any(ch.isspace() for ch in candidate):
            raise ValidationError("file_id may not contain whitespace")

    if file_name is None:
        return

    candidate = file_name.strip()
    if not candidate:
        raise ValidationError("file_name cannot be blank")
    lowered = candidate.lower()
    if "//" in lowered:
        raise ValidationError(
            "remote file references are not supported in offline mode"
        )
    if any(part == ".." for part in PurePath(candidate).parts):
        raise ValidationError("relative path traversal is not allowed")
    if "\n" in candidate or "\r" in candidate:
        raise ValidationError("file_name cannot contain newlines")


def validate_uploaded_file(
    *,
    path: str,
    original_filename: str,
    content_type: str | None,
    allowed_extensions: list[str],
    allowed_mimes: list[str],
    max_bytes: int,
) -> dict[str, object]:
    """Validate a persisted upload against security constraints."""

    target = Path(path)
    if not target.exists() or not target.is_file():
        raise ValidationError("uploaded file is not accessible")

    size_bytes = target.stat().st_size
    if size_bytes <= 0:
        raise ValidationError("uploaded file is empty")
    if size_bytes > max_bytes:
        raise ValidationError("uploaded file exceeds configured size limit")

    ext = Path(original_filename).suffix.lower()
    allowed = {item.lower() for item in allowed_extensions}
    if ext not in allowed:
        raise ValidationError("file extension is not permitted")

    suffixes = [s.lower() for s in Path(original_filename).suffixes]
    if len(suffixes) > 1 and any(
        suffix in _DOUBLE_EXTENSION_BLOCKLIST for suffix in suffixes[:-1]
    ):
        raise ValidationError("double extension pattern is not allowed")

    detected = filetype.guess(target)
    detected_mime = detected.mime if detected else None
    fallback_mime, _ = mimetypes.guess_type(original_filename)
    candidate_mimes = {
        mime
        for mime in [content_type, detected_mime, fallback_mime]
        if mime and mime.strip()
    }
    allowed_mime_set = {item.lower() for item in allowed_mimes}
    if not candidate_mimes:
        candidate_mimes.add("application/octet-stream")
    if not any(mime.lower() in allowed_mime_set for mime in candidate_mimes):
        raise ValidationError("uploaded file type is not accepted")

    return {
        "size_bytes": size_bytes,
        "mime": next(iter(candidate_mimes)),
    }
