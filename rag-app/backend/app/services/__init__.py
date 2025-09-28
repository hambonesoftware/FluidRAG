"""Domain services for the FluidRAG backend."""

from .chunk_service import run_uf_chunking as run_chunking

__all__ = ["run_chunking"]
