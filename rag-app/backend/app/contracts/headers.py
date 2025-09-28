"""Contracts for header detection and section rechunking."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HeaderArtifact(BaseModel):
    """Normalized header metadata persisted to ``headers.json``."""

    header_id: str
    doc_id: str
    text: str
    level: int = Field(
        ge=1, description="Heading depth inferred from numbering/typography"
    )
    score: float = Field(ge=0.0, le=1.0)
    recovered: bool = Field(
        default=False,
        description="True when sequence repair promoted a low-confidence candidate",
    )
    ordinal: int | None = Field(
        default=None, ge=0, description="Numeric ordinal for ordered headers"
    )
    section_key: str = Field(description="Series key used for grouping related headers")
    chunk_ids: list[str] = Field(
        default_factory=list,
        description="UF chunk identifiers contributing to the header text",
    )
    sentence_start: int = Field(ge=0)
    sentence_end: int = Field(ge=0)


class SectionAssignment(BaseModel):
    """Mapping from UF chunk to the section/header it belongs to."""

    section_id: str
    header_id: str
    chunk_id: str
    order: int = Field(ge=0)


class HeaderChunk(BaseModel):
    """Aggregated chunk aligned to a header section."""

    section_id: str
    header_id: str
    doc_id: str
    text: str
    chunk_ids: list[str] = Field(default_factory=list)
    header_text: str
    level: int = Field(ge=1)
    score: float = Field(ge=0.0, le=1.0)
    recovered: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["HeaderArtifact", "SectionAssignment", "HeaderChunk"]
