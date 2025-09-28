"""Tests for configuration utilities."""

from __future__ import annotations

from importlib import reload

import pytest

from backend.app import config
from backend.app.config import Settings, get_settings


def reset_settings_cache() -> None:
    get_settings.cache_clear()  # type: ignore[attr-defined]
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
