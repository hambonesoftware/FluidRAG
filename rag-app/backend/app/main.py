"""App factory; registers routers and returns FastAPI instance."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .util.logging import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    """App factory; registers routers and returns FastAPI instance."""
    settings = get_settings()
    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    async def healthcheck() -> dict[str, str]:
        """Simple readiness probe."""
        return {"status": "ok", "service": settings.app_name}

    @app.on_event("startup")
    async def _startup_event() -> None:
        logger.info("backend.startup", extra={"backend": settings.backend_address})

    @app.on_event("shutdown")
    async def _shutdown_event() -> None:
        logger.info("backend.shutdown")

    return app


__all__ = ["create_app"]
