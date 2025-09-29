"""Structured logging helpers with correlation IDs and spans."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_LOGGER_INITIALIZED = False
_CORRELATION_ID: ContextVar[str | None] = ContextVar(
    "fluidrag_correlation_id", default=None
)


class JsonFormatter(logging.Formatter):
    """Render log records as structured JSON."""

    STANDARD_ATTRS = {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
    }

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)
            ),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        correlation_id = getattr(record, "correlation_id", None) or get_correlation_id()
        if correlation_id:
            payload["correlation_id"] = correlation_id
        for attr in ("span", "status", "duration_ms"):
            value = getattr(record, attr, None)
            if value is not None:
                payload[attr] = value
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self.STANDARD_ATTRS
        }
        payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


class CorrelationIdFilter(logging.Filter):
    """Attach the current correlation ID to log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        correlation_id = get_correlation_id()
        if correlation_id and not getattr(record, "correlation_id", None):
            record.correlation_id = correlation_id
        return True


def _configure_root_logger(level: str) -> None:
    global _LOGGER_INITIALIZED
    if _LOGGER_INITIALIZED:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(CorrelationIdFilter())

    root_logger = logging.getLogger("fluidrag")
    root_logger.setLevel(level.upper())
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.propagate = False
    _LOGGER_INITIALIZED = True


def _load_level() -> str:
    try:
        from ..config import get_settings

        return get_settings().log_level
    except Exception:  # pragma: no cover - defensive default
        return "INFO"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return configured JSON logger."""

    _configure_root_logger(_load_level())
    base = "fluidrag"
    if name:
        logger_name = name if name.startswith(base) else f"{base}.{name}"
    else:
        logger_name = base
    return logging.getLogger(logger_name)


def generate_correlation_id() -> str:
    """Return a random correlation identifier."""

    return uuid.uuid4().hex


def get_correlation_id() -> str | None:
    """Fetch the current correlation identifier, if present."""

    return _CORRELATION_ID.get()


@contextmanager
def correlation_context(correlation_id: str | None = None) -> Iterator[str]:
    """Context manager that establishes a correlation ID."""

    correlation = correlation_id or generate_correlation_id()
    token = _CORRELATION_ID.set(correlation)
    try:
        yield correlation
    finally:  # pragma: no branch - deterministic reset
        _CORRELATION_ID.reset(token)


@contextmanager
def log_span(
    name: str,
    *,
    logger: logging.Logger | None = None,
    level: int = logging.INFO,
    extra: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Record a timing span with the configured logger."""

    span_logger = logger or get_logger("fluidrag.span")
    metadata: dict[str, Any] = dict(extra or {})
    start = time.perf_counter()
    try:
        yield metadata
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000.0
        span_logger.exception(
            "span.error",
            extra={
                **metadata,
                "span": name,
                "status": "error",
                "duration_ms": round(duration_ms, 3),
                "error": str(exc),
            },
        )
        raise
    else:
        duration_ms = (time.perf_counter() - start) * 1000.0
        status = metadata.pop("status", "ok")
        span_logger.log(
            level,
            "span.complete",
            extra={
                **metadata,
                "span": name,
                "status": status,
                "duration_ms": round(duration_ms, 3),
            },
        )


__all__ = [
    "get_logger",
    "get_correlation_id",
    "generate_correlation_id",
    "correlation_context",
    "log_span",
]
