"""Tests for structured logging configuration."""

from __future__ import annotations

import importlib
import json

import pytest

from backend.app import config as config_module
from backend.app.util import logging as logging_module


def _clear_settings_cache() -> None:
    cache_clear = getattr(config_module.get_settings, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()


def test_get_logger_emits_json(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "info")
    _clear_settings_cache()
    module = importlib.reload(logging_module)
    with module.correlation_context("cid-123"):
        logger = module.get_logger("fluidrag.test")
        logger.info("hello", extra={"foo": "bar"})
    captured = capsys.readouterr()
    payload = json.loads(captured.err.strip())
    assert payload["message"] == "hello"
    assert payload["foo"] == "bar"
    assert payload["level"] == "INFO"
    assert payload["name"] == "fluidrag.test"
    assert payload["correlation_id"] == "cid-123"


def test_correlation_context_generates_ids() -> None:
    module = importlib.reload(logging_module)
    with module.correlation_context() as generated:
        assert generated
        assert module.get_correlation_id() == generated
    assert module.get_correlation_id() is None


def test_log_span_emits_duration(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "info")
    _clear_settings_cache()
    module = importlib.reload(logging_module)
    logger = module.get_logger("fluidrag.span")
    with module.correlation_context("span-1"):
        with module.log_span("demo", logger=logger) as span_meta:
            span_meta["details"] = "ok"
    captured = capsys.readouterr()
    lines = [line for line in captured.err.strip().splitlines() if line]
    assert lines, "expected span log output"
    payload = json.loads(lines[-1])
    assert payload["span"] == "demo"
    assert payload["status"] == "ok"
    assert payload["details"] == "ok"
    assert payload["correlation_id"] == "span-1"
    assert payload["duration_ms"] >= 0.0
