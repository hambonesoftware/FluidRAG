"""Backend API routes for FluidRAG."""

from . import chunk, docs, headers, parser, uploads
from .chunk import router as chunk_router
from .headers import router as headers_router
from .docs import router as docs_router
from .orchestrator import router as orchestrator_router
from .parser import router as parser_router
from .passes import router as passes_router
from .uploads import router as upload_router

__all__ = [
    "uploads",
    "docs",
    "parser",
    "chunk",
    "headers",
    "upload_router",
    "parser_router",
    "chunk_router",
    "headers_router",
    "docs_router",
    "orchestrator_router",
    "passes_router",
]
