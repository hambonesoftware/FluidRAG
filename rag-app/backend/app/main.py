from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routes import (
    chunk_router,
    headers_router,
    orchestrator_router,
    parser_router,
    passes_router,
    upload_router,
)
from .util.logging import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """App factory; registers routers and returns FastAPI instance."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "backend.startup",
            extra={"backend": settings.backend_address, "offline": settings.offline},
        )
        try:
            yield
        finally:
            logger.info("backend.shutdown")

    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(upload_router)
    app.include_router(parser_router)
    app.include_router(chunk_router)
    app.include_router(headers_router)
    app.include_router(orchestrator_router)
    app.include_router(passes_router)

    @app.get("/health", tags=["system"])
    async def healthcheck() -> dict[str, str]:
        """Simple readiness probe."""
        return {"status": "ok", "service": settings.app_name}

    return app


__all__ = ["create_app"]
