"""Upload input validation."""
from __future__ import annotations

from backend.app.util.errors import ValidationError


def validate_upload_inputs(file_name: str, content_type: str, size: int) -> None:
    if not file_name:
        raise ValidationError("file_name is required")
    if size <= 0:
        raise ValidationError("Empty payload")
    allowed_types = {"application/pdf", "text/plain"}
    if content_type not in allowed_types:
        raise ValidationError(f"Unsupported content type: {content_type}")
