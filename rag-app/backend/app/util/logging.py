"""Structured logging utilities."""
from __future__ import annotations

import json
import logging
from logging import Logger
from typing import Any, Dict

from backend.app.config import settings


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: Dict[str, Any] = {
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in payload:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except TypeError:
                payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False)


_LOGGERS: dict[str, Logger] = {}


def _resolve_level(level: str | int | None) -> int:
    if level is None:
        return logging.getLevelName(settings.log_level.upper()) if isinstance(settings.log_level, str) else settings.log_level
    if isinstance(level, int):
        return level
    numeric = logging.getLevelName(level.upper())
    return numeric if isinstance(numeric, int) else logging.INFO


def get_logger(name: str | None = None, level: str | int | None = None) -> Logger:
    """Return configured JSON logger."""

    name = name or "fluidrag"
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    logger.setLevel(_resolve_level(level))
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    _LOGGERS[name] = logger
    return logger
