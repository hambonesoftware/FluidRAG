"""Chunking utilities exposed for external callers."""

from .efhg import compute_chunk_scores, run_efhg

__all__ = ["compute_chunk_scores", "run_efhg"]
