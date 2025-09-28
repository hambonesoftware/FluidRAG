"""Application-specific error hierarchy."""
from __future__ import annotations

from typing import Any, Dict, Optional


class AppError(RuntimeError):
    """Base class for application errors with structured payloads."""

    def __init__(self, message: str, *, context: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        return {"message": str(self), "context": self.context, "type": self.__class__.__name__}


class ValidationError(AppError):
    """Raised when user supplied inputs fail validation."""


class NotFoundError(AppError):
    """Raised when a requested resource cannot be located."""


class ExternalServiceError(AppError):
    """Raised when an external dependency fails."""


class RetryExhaustedError(AppError):
    """Raised when a retry loop exceeds the configured attempts."""
