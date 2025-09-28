"""Logging utilities with structured defaults."""
from __future__ import annotations

import logging
from logging import Logger
from typing import Optional


_LOGGERS: dict[str, Logger] = {}


def get_logger(name: str, level: Optional[str] = None) -> Logger:
    """Return a module level logger configured once."""
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(level or logging.getLevelName(logger.level) or "INFO")
    logger.propagate = False
    _LOGGERS[name] = logger
    return logger
