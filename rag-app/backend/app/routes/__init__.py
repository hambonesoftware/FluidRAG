"""Backend API routes for FluidRAG."""

from .parser import router as parser_router
from .upload import router as upload_router

__all__ = ["parser_router", "upload_router"]
