"""Application settings resolved from environment."""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from pydantic import AliasChoices, Field
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

try:  # pragma: no cover - Python <3.11 fallback
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found]


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
    logging_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices(
            "LOG_LEVEL", "logging_level", "logging.level"
        ),
    )
    logging_json: bool = Field(
        default=True,
        validation_alias=AliasChoices("LOG_JSON", "logging_json", "logging.json"),
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
    upload_max_mb: int = Field(
        default=100,
        ge=1,
        validation_alias=AliasChoices("UPLOAD_MAX_MB", "upload.max_mb"),
    )
    upload_max_bytes: int | None = Field(
        default=None,
        ge=1,
        validation_alias=AliasChoices(
            "UPLOAD_MAX_BYTES",
            "upload_max_bytes",
            "upload.max_bytes",
        ),
    )
    upload_allowed_ext: tuple[str, ...] = Field(
        default=(".pdf",),
        validation_alias=AliasChoices(
            "UPLOAD_ALLOWED_EXT", "upload_allowed_ext", "upload.allowed_ext"
        ),
    )
    upload_allowed_mime: tuple[str, ...] = Field(
        default=("application/pdf",),
        validation_alias=AliasChoices(
            "UPLOAD_ALLOWED_MIME",
            "upload_allowed_mime",
            "upload.allowed_mime",
        ),
    )
    upload_storage_temp: str = Field(
        default="storage/uploads/tmp",
        validation_alias=AliasChoices(
            "UPLOAD_STORAGE_TEMP", "upload.storage.temp"
        ),
    )
    upload_storage_final: str = Field(
        default="storage/uploads/final",
        validation_alias=AliasChoices(
            "UPLOAD_STORAGE_FINAL", "upload.storage.final"
        ),
    )
    upload_rate_limit_per_minute: int = Field(
        default=60,
        ge=1,
        validation_alias=AliasChoices(
            "UPLOAD_RATE_LIMIT_PER_MINUTE", "upload.rate_limit.per_minute"
        ),
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
    parser_ocr_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("PARSER_OCR_ENABLED", "parser.ocr.enabled"),
    )
    parser_ocr_languages: tuple[str, ...] = Field(
        default=("eng",),
        validation_alias=AliasChoices(
            "PARSER_OCR_LANGUAGES",
            "parser_ocr_languages",
            "parser.ocr.languages",
        ),
    )
    parser_tuning_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "PARSER_TUNING_ENABLED", "parser.tuning.enabled"
        ),
    )
    parser_efhg_weights_regex: float = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "PARSER_EFHG_WEIGHTS_REGEX", "parser.efhg.weights.regex"
        ),
    )
    parser_efhg_weights_style: float = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "PARSER_EFHG_WEIGHTS_STYLE", "parser.efhg.weights.style"
        ),
    )
    parser_efhg_weights_entropy: float = Field(
        default=0.8,
        validation_alias=AliasChoices(
            "PARSER_EFHG_WEIGHTS_ENTROPY", "parser.efhg.weights.entropy"
        ),
    )
    parser_efhg_weights_graph: float = Field(
        default=1.1,
        validation_alias=AliasChoices(
            "PARSER_EFHG_WEIGHTS_GRAPH", "parser.efhg.weights.graph"
        ),
    )
    parser_efhg_weights_fluid: float = Field(
        default=0.9,
        validation_alias=AliasChoices(
            "PARSER_EFHG_WEIGHTS_FLUID", "parser.efhg.weights.fluid"
        ),
    )
    parser_efhg_weights_llm_vote: float = Field(
        default=1.0,
        validation_alias=AliasChoices(
            "PARSER_EFHG_WEIGHTS_LLM_VOTE",
            "parser.efhg.weights.llm_vote",
        ),
    )
    parser_efhg_thresholds_header: float = Field(
        default=0.65,
        validation_alias=AliasChoices(
            "PARSER_EFHG_THRESHOLDS_HEADER",
            "parser.efhg.thresholds.header",
        ),
    )
    parser_efhg_thresholds_subheader: float = Field(
        default=0.5,
        validation_alias=AliasChoices(
            "PARSER_EFHG_THRESHOLDS_SUBHEADER",
            "parser.efhg.thresholds.subheader",
        ),
    )
    parser_efhg_stitching_adjacency_weight: float = Field(
        default=0.8,
        validation_alias=AliasChoices(
            "PARSER_EFHG_STITCHING_ADJACENCY_WEIGHT",
            "parser.efhg.stitching.adjacency_weight",
        ),
    )
    parser_efhg_stitching_entropy_join_delta: float = Field(
        default=0.15,
        validation_alias=AliasChoices(
            "PARSER_EFHG_STITCHING_ENTROPY_JOIN_DELTA",
            "parser.efhg.stitching.entropy_join_delta",
        ),
    )
    parser_efhg_stitching_style_cont_threshold: float = Field(
        default=0.7,
        validation_alias=AliasChoices(
            "PARSER_EFHG_STITCHING_STYLE_CONT_THRESHOLD",
            "parser.efhg.stitching.style_cont_threshold",
        ),
    )
    parser_sequence_repair_hole_penalty: float = Field(
        default=0.4,
        validation_alias=AliasChoices(
            "PARSER_SEQUENCE_REPAIR_HOLE_PENALTY",
            "parser.sequence_repair.hole_penalty",
        ),
    )
    parser_sequence_repair_max_gap_span_pages: int = Field(
        default=2,
        validation_alias=AliasChoices(
            "PARSER_SEQUENCE_REPAIR_MAX_GAP_SPAN_PAGES",
            "parser.sequence_repair.max_gap_span_pages",
        ),
    )
    parser_sequence_repair_min_schema_support: int = Field(
        default=2,
        validation_alias=AliasChoices(
            "PARSER_SEQUENCE_REPAIR_MIN_SCHEMA_SUPPORT",
            "parser.sequence_repair.min_schema_support",
        ),
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
    cors_allowed_origins: tuple[str, ...] = Field(
        default=("*",),
        validation_alias=AliasChoices(
            "CORS_ALLOWED_ORIGINS", "cors.allowed_origins"
        ),
    )
    cors_allowed_methods: tuple[str, ...] = Field(
        default=("GET", "POST"),
        validation_alias=AliasChoices(
            "CORS_ALLOWED_METHODS", "cors.allowed_methods"
        ),
    )
    cors_allowed_headers: tuple[str, ...] = Field(
        default=("Authorization", "Content-Type"),
        validation_alias=AliasChoices(
            "CORS_ALLOWED_HEADERS", "cors.allowed_headers"
        ),
    )

    def __init__(self, **data: Any) -> None:
        """Pydantic settings init"""
        super().__init__(**data)

    @property
    def log_level(self) -> str:
        """Return configured logging level."""

        return str(self.logging_level).lower()

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

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Prepend TOML config sources before env and init data."""

        return (
            cls._toml_settings_source(settings_cls),
            env_settings,
            dotenv_settings,
            init_settings,
            file_secret_settings,
        )

    @classmethod
    def _toml_settings_source(
        cls, settings_cls: type[BaseSettings]
    ) -> PydanticBaseSettingsSource:
        class TomlSource(PydanticBaseSettingsSource):
            def __init__(self, settings_cls: type[BaseSettings]) -> None:
                super().__init__(settings_cls)
                self._cache: dict[str, Any] | None = None

            def _load(self) -> dict[str, Any]:
                if self._cache is None:
                    base = Path(__file__).resolve().parents[3]
                    config_path = base / "configs" / "app.toml"
                    tuned_path = base / "configs" / "tuned" / "header_detector.toml"
                    data: dict[str, Any] = {}
                    if config_path.exists():
                        with config_path.open("rb") as handle:
                            data.update(cls._flatten_config(tomllib.load(handle)))
                    if tuned_path.exists():
                        with tuned_path.open("rb") as handle:
                            tuned_flat = cls._flatten_config(tomllib.load(handle))
                        data.update({k: v for k, v in tuned_flat.items() if k.startswith("parser_")})
                    self._cache = data
                return dict(self._cache)

            def __call__(self) -> dict[str, Any]:
                return self._load()

            def get_field_value(
                self,
                field: FieldInfo,
                field_name: str,
            ) -> tuple[Any | None, str, bool]:
                data = self._load()
                if field_name in data:
                    return data[field_name], field_name, True
                return None, field_name, False

        return TomlSource(settings_cls)

    @staticmethod
    def _flatten_config(config: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
        flattened: dict[str, Any] = {}
        for key, value in config.items():
            safe_key = key.replace("-", "_")
            composite = f"{prefix}_{safe_key}" if prefix else safe_key
            if isinstance(value, Mapping):
                flattened.update(Settings._flatten_config(value, composite))
            else:
                flattened[composite] = value
        return flattened

    def audit_retention_window(self) -> timedelta:
        """Return retention window for audit artifacts as ``timedelta``."""

        return timedelta(days=self.audit_retention_days)

    def storage_chunk_bytes(self) -> int:
        """Return chunk size for streaming I/O operations."""

        return int(self.storage_stream_chunk_size)

    def max_upload_bytes(self) -> int:
        """Return the configured upload size ceiling in bytes."""

        if self.upload_max_bytes is not None:
            return int(self.upload_max_bytes)
        return int(self.upload_max_mb * 1024 * 1024)

    def openrouter_retry_schedule(self) -> list[float]:
        """Return exponential backoff schedule for OpenRouter calls."""

        retries = max(int(self.openrouter_max_retries), 0)
        base = max(float(self.openrouter_backoff_base_seconds), 0.0)
        cap = max(float(self.openrouter_backoff_cap_seconds), 0.0)

        schedule: list[float] = [0.0]
        if retries == 0:
            return schedule

        delay = base
        for _ in range(retries):
            if cap > 0.0:
                schedule.append(min(delay, cap))
            else:
                schedule.append(delay)
            delay = delay * 2 if delay > 0.0 else base
            if cap > 0.0 and delay > cap:
                delay = cap
        return schedule


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance."""
    return Settings()


__all__ = ["Settings", "get_settings"]
