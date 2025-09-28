"""Contracts emitted from the parser service."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ParseArtifact(BaseModel):
    """Structured representation of parser outputs."""

    doc_id: str
    enriched_path: str
    language: str = Field(default="und", min_length=2)
    summary: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)


__all__ = ["ParseArtifact"]
