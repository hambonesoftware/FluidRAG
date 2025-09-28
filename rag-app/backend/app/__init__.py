"""Application package."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - imported only for type checking
    from fastapi import FastAPI


def create_app() -> "FastAPI":
    """Return the FastAPI application instance.

    Importing :mod:`fastapi` at module import time makes the package unusable in
    environments where the optional web dependencies are not installed.  The
    test-suite only needs to import the application package, so we defer the
    heavy import until the factory is actually invoked.  This keeps the module
    lightweight while preserving the original public API.
    """

    from .main import create_app as _create_app

    return _create_app()


__all__ = ["create_app"]
