from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .config import get_settings
from .routes import (
    chunk_router,
    headers_router,
    orchestrator_router,
    parser_router,
    passes_router,
    upload_router,
)
from .util.logging import correlation_context, generate_correlation_id, get_logger

logger = get_logger(__name__)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Request middleware that manages correlation IDs and timing."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        correlation_id = (
            request.headers.get("x-correlation-id") or generate_correlation_id()
        )
        with correlation_context(correlation_id):
            start = perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                duration_ms = (perf_counter() - start) * 1000.0
                logger.exception(
                    "request.error",
                    extra={
                        "path": request.url.path,
                        "method": request.method,
                        "duration_ms": round(duration_ms, 3),
                    },
                )
                raise
            duration_ms = (perf_counter() - start) * 1000.0
            response.headers["x-correlation-id"] = correlation_id
            response.headers["x-response-time-ms"] = f"{duration_ms:.3f}"
            logger.info(
                "request.complete",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            return response


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

    app.add_middleware(ObservabilityMiddleware)
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
