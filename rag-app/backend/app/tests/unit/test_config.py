"""Tests for configuration utilities."""

from __future__ import annotations

from importlib import reload
from pathlib import Path

import pytest

from backend.app import config
from backend.app.config import Settings, get_settings


def reset_settings_cache() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()
    reload(config)


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_settings_cache()
    settings = Settings()
    assert settings.backend_host == "127.0.0.1"
    assert settings.backend_port == 8000
    assert settings.frontend_port == 3000
    assert settings.log_level == "info"


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKEND_PORT", "9001")
    monkeypatch.setenv("FRONTEND_PORT", "3999")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    reset_settings_cache()
    settings = get_settings()
    assert settings.backend_port == 9001
    assert settings.frontend_port == 3999
    assert settings.log_level == "debug"


def test_uvicorn_and_frontend_options(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BACKEND_RELOAD", raising=False)
    reset_settings_cache()
    settings = Settings(backend_reload=True, backend_port=8123, frontend_port=3123)
    uvicorn_opts = settings.uvicorn_options()
    assert uvicorn_opts == {
        "host": "127.0.0.1",
        "port": 8123,
        "reload": True,
        "log_level": "info",
    }
    frontend_opts = settings.frontend_options()
    assert frontend_opts == {"host": "127.0.0.1", "port": 3123}


def test_address_and_artifact_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    settings = Settings(artifact_root=str(artifact_root))
    assert settings.backend_address == "127.0.0.1:8000"
    assert settings.frontend_address == "127.0.0.1:3000"
    assert settings.artifact_root_path.is_absolute()

    absolute_root = (tmp_path / "absolute").resolve()
    absolute_root.mkdir()
    monkeypatch.setenv("ARTIFACT_ROOT", str(absolute_root))
    reset_settings_cache()
    settings = get_settings()
    assert settings.artifact_root_path == absolute_root


def test_openrouter_retry_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_MAX_RETRIES", "2")
    monkeypatch.setenv("OPENROUTER_BACKOFF_BASE_SECONDS", "0.25")
    monkeypatch.setenv("OPENROUTER_BACKOFF_CAP_SECONDS", "1.0")
    reset_settings_cache()
    settings = get_settings()
    assert settings.openrouter_retry_schedule() == [0.0, 0.25, 0.5]


def test_audit_and_storage_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "21")
    monkeypatch.setenv("STORAGE_STREAM_CHUNK_SIZE", "2048")
    reset_settings_cache()
    settings = get_settings()
    assert settings.audit_retention_window().days == 21
    assert settings.storage_chunk_bytes() == 2048
