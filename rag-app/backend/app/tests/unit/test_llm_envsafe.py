"""Tests for OpenRouter env helpers."""

from __future__ import annotations

import pytest

from ...llm.utils.envsafe import mask_bearer, masked_headers, openrouter_headers


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_HTTP_REFERER", raising=False)
    monkeypatch.delenv("OPENROUTER_APP_TITLE", raising=False)


def test_mask_bearer_masks_middle() -> None:
    assert mask_bearer("abcd1234efgh5678") == "abcd...5678"


def test_mask_bearer_handles_short_values() -> None:
    assert mask_bearer("abc") == "***"
    assert mask_bearer(None) == ""


def test_openrouter_headers_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(RuntimeError):
        openrouter_headers()
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "https://example.com")
    monkeypatch.setenv("OPENROUTER_APP_TITLE", "FluidRAG Test")
    headers = openrouter_headers()
    assert headers["Authorization"] == "Bearer sk-test"
    assert headers["HTTP-Referer"] == "https://example.com"
    assert headers["X-Title"] == "FluidRAG Test"
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept"] == "application/json"


def test_masked_headers_masks_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "secret-key-9876")
    headers = openrouter_headers()
    masked = masked_headers(headers)
    assert masked["Authorization"].startswith("Bearer ")
    assert "..." in masked["Authorization"]
    # ensure original dict not mutated
    assert headers["Authorization"].endswith("9876")
    assert headers["Authorization"] != masked["Authorization"]
