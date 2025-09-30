"""Upload input validation utilities."""

from __future__ import annotations

from pathlib import Path, PurePath

from .....config import get_settings

from .....util.errors import ValidationError


def validate_upload_inputs(
    file_id: str | None = None,
    file_name: str | None = None,
    *,
    upload_bytes: bytes | None = None,
    upload_filename: str | None = None,
) -> None:
    """Raise on invalid upload inputs."""
    settings = get_settings()
    allowed_extensions = {
        ext if ext.startswith(".") else f".{ext}"
        for ext in settings.upload_allowed_ext
    }
    max_bytes = int(settings.upload_max_mb * 1024 * 1024)

    if upload_bytes is not None:
        if file_id or file_name:
            raise ValidationError("direct uploads cannot specify file_id or file_name")
        if not upload_bytes:
            raise ValidationError("uploaded file is empty")
        if len(upload_bytes) > max_bytes:
            raise ValidationError(
                f"file exceeds maximum size of {max_bytes} bytes"
            )
        candidate = (upload_filename or "uploaded.pdf").strip()
        if not candidate:
            raise ValidationError("upload_filename cannot be blank")
        suffix = Path(candidate).suffix.lower() or ".pdf"
        if suffix not in allowed_extensions:
            raise ValidationError(
                f"unsupported file extension: {suffix or '[none]'}"
            )
        return

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

    path = Path(candidate).expanduser()
    if not path.exists() or not path.is_file():
        raise ValidationError("file_name does not reference an existing file")
    suffix = path.suffix.lower()
    if suffix not in allowed_extensions:
        raise ValidationError(
            f"unsupported file extension: {suffix or '[none]'}"
        )
    file_size = path.stat().st_size
    if file_size > max_bytes:
        raise ValidationError(
            f"file exceeds maximum size of {max_bytes} bytes"
        )
