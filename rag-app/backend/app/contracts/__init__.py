"""Pydantic contracts shared across services."""

from .chunking import HybridSearchResult, UFChunk

__all__ = ["UFChunk", "HybridSearchResult"]
