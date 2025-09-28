"""Tests for structured logging configuration."""
from __future__ import annotations

import importlib
import json

import pytest

from backend.app import config as config_module
from backend.app.util import logging as logging_module


def test_get_logger_emits_json(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "info")
    config_module.get_settings.cache_clear()  # type: ignore[attr-defined]
    module = importlib.reload(logging_module)
    logger = module.get_logger("fluidrag.test")
    logger.info("hello", extra={"foo": "bar"})
    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())
    assert payload["message"] == "hello"
    assert payload["foo"] == "bar"
    assert payload["level"] == "INFO"
    assert payload["name"] == "fluidrag.test"
