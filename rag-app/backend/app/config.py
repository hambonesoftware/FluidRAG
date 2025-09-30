"""Application settings resolved from environment."""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings resolved from environment."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = Field(
        default="FluidRAG", validation_alias=AliasChoices("APP_NAME", "app_name")
    )
    backend_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("BACKEND_HOST", "backend_host"),
    )
    backend_port: int = Field(
        default=8000, validation_alias=AliasChoices("BACKEND_PORT", "backend_port")
    )
    backend_reload: bool = Field(
        default=False, validation_alias=AliasChoices("BACKEND_RELOAD", "backend_reload")
    )
    frontend_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("FRONTEND_HOST", "frontend_host"),
    )
    frontend_port: int = Field(
        default=3000, validation_alias=AliasChoices("FRONTEND_PORT", "frontend_port")
    )
    log_level: str = Field(
        default="info", validation_alias=AliasChoices("LOG_LEVEL", "log_level")
    )
    offline: bool = Field(
        default=True,
        validation_alias=AliasChoices("FLUIDRAG_OFFLINE", "fluidrag_offline"),
    )
    artifact_root: str = Field(
        default="rag-app/data/artifacts",
        validation_alias=AliasChoices("ARTIFACT_ROOT", "artifact_root"),
    )
    upload_allowed_extensions: list[str] = Field(
        default_factory=lambda: [".pdf"],
        validation_alias=AliasChoices(
            "UPLOAD_ALLOWED_EXTENSIONS", "upload_allowed_extensions"
        ),
    )
    upload_max_size_mb: int = Field(
        default=64,
        ge=1,
        validation_alias=AliasChoices(
            "UPLOAD_MAX_SIZE_MB", "upload_max_size_mb"
        ),
    )
    upload_mime_allowlist: list[str] = Field(
        default_factory=lambda: [
            "application/pdf",
            "application/x-pdf",
            "application/octet-stream",
        ],
        validation_alias=AliasChoices(
            "UPLOAD_MIME_ALLOWLIST",
            "upload_mime_allowlist",
        ),
    )
    upload_ocr_threshold: float = Field(
        default=0.85,
        validation_alias=AliasChoices("UPLOAD_OCR_THRESHOLD", "upload_ocr_threshold"),
    )
    chunk_target_tokens: int = Field(
        default=90,
        ge=10,
        validation_alias=AliasChoices("CHUNK_TARGET_TOKENS", "chunk_target_tokens"),
    )
    chunk_token_overlap: int = Field(
        default=12,
        ge=0,
        validation_alias=AliasChoices("CHUNK_TOKEN_OVERLAP", "chunk_token_overlap"),
    )
    parser_timeout_seconds: float = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "PARSER_TIMEOUT_SECONDS", "parser_timeout_seconds"
        ),
    )
    openrouter_timeout_seconds: float = Field(
        default=45.0,
        ge=1.0,
        validation_alias=AliasChoices(
            "OPENROUTER_TIMEOUT_SECONDS", "openrouter_timeout_seconds"
        ),
    )
    openrouter_max_retries: int = Field(
        default=3,
        ge=0,
        validation_alias=AliasChoices(
            "OPENROUTER_MAX_RETRIES", "openrouter_max_retries"
        ),
    )
    openrouter_backoff_base_seconds: float = Field(
        default=0.5,
        ge=0.0,
        validation_alias=AliasChoices(
            "OPENROUTER_BACKOFF_BASE_SECONDS",
            "openrouter_backoff_base_seconds",
        ),
    )
    openrouter_backoff_cap_seconds: float = Field(
        default=6.0,
        ge=0.0,
        validation_alias=AliasChoices(
            "OPENROUTER_BACKOFF_CAP_SECONDS",
            "openrouter_backoff_cap_seconds",
        ),
    )
    openrouter_stream_idle_timeout_seconds: float = Field(
        default=4.0,
        ge=0.5,
        validation_alias=AliasChoices(
            "OPENROUTER_STREAM_IDLE_TIMEOUT_SECONDS",
            "openrouter_stream_idle_timeout_seconds",
        ),
    )
    vector_batch_size: int = Field(
        default=128,
        ge=1,
        validation_alias=AliasChoices(
            "VECTOR_BATCH_SIZE",
            "vector_batch_size",
        ),
    )
    llm_batch_size: int = Field(
        default=4,
        ge=1,
        validation_alias=AliasChoices("LLM_BATCH_SIZE", "llm_batch_size"),
    )
    audit_retention_days: int = Field(
        default=14,
        ge=1,
        validation_alias=AliasChoices(
            "AUDIT_RETENTION_DAYS",
            "audit_retention_days",
        ),
    )
    storage_stream_chunk_size: int = Field(
        default=65536,
        ge=1024,
        validation_alias=AliasChoices(
            "STORAGE_STREAM_CHUNK_SIZE",
            "storage_stream_chunk_size",
        ),
    )

    def __init__(self, **data: Any) -> None:
        """Pydantic settings init"""
        super().__init__(**data)

    @property
    def backend_address(self) -> str:
        """Return the ``host:port`` pair for the FastAPI server."""
        return f"{self.backend_host}:{self.backend_port}"

    @property
    def frontend_address(self) -> str:
        """Return the ``host:port`` pair for the static frontend server."""
        return f"{self.frontend_host}:{self.frontend_port}"

    @property
    def artifact_root_path(self) -> Path:
        """Return the absolute path for storing artifacts."""
        base = Path(__file__).resolve().parents[3]
        root = Path(self.artifact_root)
        if root.is_absolute():
            return root
        return (base / root).resolve()

    def uvicorn_options(self) -> dict[str, Any]:
        """Return keyword arguments for configuring Uvicorn."""
        return {
            "host": self.backend_host,
            "port": self.backend_port,
            "reload": self.backend_reload,
            "log_level": self.log_level,
        }

    def frontend_options(self) -> dict[str, Any]:
        """Return parameters for the static HTTP server."""
        return {
            "host": self.frontend_host,
            "port": self.frontend_port,
        }

    def openrouter_retry_schedule(self) -> list[float]:
        """Return deterministic exponential backoff durations in seconds."""

        retries = max(self.openrouter_max_retries, 0)
        base = max(self.openrouter_backoff_base_seconds, 0.0)
        cap = max(self.openrouter_backoff_cap_seconds, 0.0)
        schedule: list[float] = [0.0]
        for attempt in range(1, retries + 1):
            delay = min(cap, base * (2 ** (attempt - 1)))
            schedule.append(round(delay, 4))
        return schedule

    def audit_retention_window(self) -> timedelta:
        """Return retention window for audit artifacts as ``timedelta``."""

        return timedelta(days=self.audit_retention_days)

    def storage_chunk_bytes(self) -> int:
        """Return chunk size for streaming I/O operations."""

        return int(self.storage_stream_chunk_size)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()


__all__ = ["Settings", "get_settings"]
