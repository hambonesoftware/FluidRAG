"""Application settings resolved from environment."""

from __future__ import annotations

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
    upload_ocr_threshold: float = Field(
        default=0.85,
        validation_alias=AliasChoices("UPLOAD_OCR_THRESHOLD", "upload_ocr_threshold"),
    )
    parser_timeout_seconds: float = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "PARSER_TIMEOUT_SECONDS", "parser_timeout_seconds"
        ),
    )

    def __init__(self, **data: Any) -> None:
        """Pydantic settings init."""
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()


__all__ = ["Settings", "get_settings"]
