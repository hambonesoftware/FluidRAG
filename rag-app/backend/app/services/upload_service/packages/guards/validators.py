"""Upload input validation utilities."""

from __future__ import annotations

from pathlib import PurePath

from .....util.errors import ValidationError


def validate_upload_inputs(
    file_id: str | None = None, file_name: str | None = None
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
