"""Common application errors."""

from __future__ import annotations


class AppError(Exception):
    """Base application error."""


class ValidationError(AppError):
    """Input validation error."""


class NotFoundError(AppError):
    """Resource not found."""


class ExternalServiceError(AppError):
    """Downstream service failure."""


class RetryExhaustedError(AppError):
    """Retries exhausted."""


__all__ = [
    "AppError",
    "ValidationError",
    "NotFoundError",
    "ExternalServiceError",
    "RetryExhaustedError",
]
