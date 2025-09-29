"""Tests for the offline LLM adapter."""

from __future__ import annotations

import pytest

from ...adapters.llm import LLMClient, call_llm
from ...config import get_settings
from ...util.errors import ExternalServiceError


def test_call_llm_offline_returns_synthesized_answer() -> None:
    get_settings.cache_clear()
    result = call_llm("system", "Question?", "Line one.\nLine two.")
    assert result["provider"] == "offline-synth"
    assert "Answer:" in result["content"]
    assert result["tokens"]["prompt"] > 0


def test_llm_client_embed_is_deterministic() -> None:
    client = LLMClient()
    first = client.embed(["hello"])[0]
    second = client.embed(["hello"])[0]
    assert first == second
    assert len(first) == 16


def test_llm_client_raises_when_online(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLUIDRAG_OFFLINE", "false")
    get_settings.cache_clear()
    client = LLMClient()
    with pytest.raises(ExternalServiceError):
        client.chat("system", "user", "context")
    get_settings.cache_clear()
