"""FastAPI application factory."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes import orchestrator, upload, parser, chunk, headers, passes
from .util.logging import get_logger

logger = get_logger(__name__, settings.log_level)


def create_app() -> FastAPI:
    app = FastAPI(title="FluidRAG", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(upload.router)
    app.include_router(parser.router)
    app.include_router(chunk.router)
    app.include_router(headers.router)
    app.include_router(passes.router)
    app.include_router(orchestrator.router)

    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - FastAPI hook
        logger.info("Application startup complete")

    return app
