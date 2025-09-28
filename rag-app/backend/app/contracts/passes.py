"""Contracts describing pass results and retrieval metadata."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RetrievalTrace(BaseModel):
    """Trace entry describing retrieval provenance for a chunk."""

    chunk_id: str
    header_path: str | None = None
    score: float = Field(default=0.0)
    dense_score: float = Field(default=0.0)
    sparse_score: float = Field(default=0.0)
    flow_score: float = Field(default=0.0)
    energy_score: float = Field(default=0.0)
    graph_score: float = Field(default=0.0)
    text_preview: str = Field(default="", max_length=512)


class Citation(BaseModel):
    """Citation referencing the section + chunk used for the answer."""

    chunk_id: str
    header_path: str | None = None
    sentence_start: int | None = None
    sentence_end: int | None = None


class PassResult(BaseModel):
    """JSON payload persisted for each domain pass."""

    doc_id: str
    pass_id: str
    pass_name: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    retrieval: list[RetrievalTrace] = Field(default_factory=list)
    context: str
    prompt: dict[str, Any] = Field(default_factory=dict)


class PassManifest(BaseModel):
    """Manifest describing all generated passes for a document."""

    doc_id: str
    passes: dict[str, str] = Field(default_factory=dict)


__all__ = [
    "RetrievalTrace",
    "Citation",
    "PassResult",
    "PassManifest",
]
