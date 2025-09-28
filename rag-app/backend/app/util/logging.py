"""Return configured JSON logger."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

_LOGGER_INITIALIZED = False


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
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in self.STANDARD_ATTRS
        }
        payload.update(extra)
        return json.dumps(payload, ensure_ascii=False)


def _configure_root_logger(level: str) -> None:
    global _LOGGER_INITIALIZED
    if _LOGGER_INITIALIZED:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger("fluidrag")
    root_logger.setLevel(level.upper())
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.propagate = False
    _LOGGER_INITIALIZED = True


def get_logger(name: str = None) -> logging.Logger:
    """Return configured JSON logger."""
    try:
        from ..config import get_settings  # Local import to avoid circular dependency.

        level = get_settings().log_level
    except Exception:  # pragma: no cover - defensive default when settings unavailable
        level = "INFO"

    _configure_root_logger(level)
    return logging.getLogger(name or "fluidrag")


__all__ = ["get_logger"]
