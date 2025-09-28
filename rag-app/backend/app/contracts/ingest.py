"""Contracts describing ingestion/normalization outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NormalizedManifest(BaseModel):
    """Metadata emitted by the upload normalization stage."""

    doc_id: str
    normalized_path: str
    manifest_path: str
    checksum: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    block_count: int = Field(default=0, ge=0)
    avg_coverage: float = Field(default=0.0, ge=0.0)
    ocr_performed: bool = False
    extras: dict[str, Any] = Field(default_factory=dict)


__all__ = ["NormalizedManifest"]
