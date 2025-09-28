"""Application settings."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class Settings:
    env: str
    data_dir: Path
    storage_dir: Path
    log_level: str
    openrouter_api_key: str | None
    openrouter_base_url: str

    def __init__(self) -> None:
        self.env = os.getenv("APP_ENV", "development")
        base_dir = Path(os.getenv("APP_STORAGE_DIR", "./data")).resolve()
        self.data_dir = Path(os.getenv("APP_DATA_DIR", base_dir / "artifacts")).resolve()
        self.storage_dir = base_dir
        self.log_level = os.getenv("APP_LOG_LEVEL", "INFO")
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
