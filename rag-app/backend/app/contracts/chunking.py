"""Contracts for chunking and retrieval."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UFChunk(BaseModel):
    """Universal format chunk representation."""

    chunk_id: str
    doc_id: str
    text: str
    sentence_start: int = Field(ge=0)
    sentence_end: int = Field(ge=0)
    token_count: int = Field(ge=0)
    typography: dict[str, Any] = Field(default_factory=dict)


class HybridSearchResult(BaseModel):
    """Result row from hybrid search fusion."""

    chunk_index: int = Field(ge=0)
    score: float
    dense_score: float
    sparse_score: float


__all__ = ["UFChunk", "HybridSearchResult"]
