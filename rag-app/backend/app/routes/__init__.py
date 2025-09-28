"""Backend API routes for FluidRAG."""

from .chunk import router as chunk_router
from .parser import router as parser_router
from .upload import router as upload_router

__all__ = ["upload_router", "parser_router", "chunk_router"]
