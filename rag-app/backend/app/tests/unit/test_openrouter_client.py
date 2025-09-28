"""Unit tests for the OpenRouter client helpers."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, Iterator
from typing import Any

import pytest

from ...config import get_settings
from ...llm.clients import openrouter as client_module
from ...llm.clients.openrouter import (
    OpenRouterAuthError,
    OpenRouterHTTPError,
    OpenRouterStreamError,
    chat_stream_async,
    chat_sync,
    embed_sync,
)


class DummyResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)

    def json(self) -> dict[str, Any]:
        return self._payload


class MockClient:
    queue: list[Any] = []

    def __init__(
        self, *args: Any, **kwargs: Any
    ) -> None:  # pragma: no cover - init stub
        pass

    def __enter__(self) -> MockClient:  # pragma: no cover - context stub
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - context stub
        return None

    def post(
        self, url: str, headers: dict[str, str], json: dict[str, Any]
    ) -> DummyResponse:
        if not self.queue:
            raise AssertionError("MockClient queue exhausted")
        response = self.queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class DummyStreamResponse:
    def __init__(
        self, status_code: int, lines: list[Any], body: bytes | str = b""
    ) -> None:
        self.status_code = status_code
        self._lines = lines
        self._body = body if isinstance(body, bytes) else str(body).encode()

    async def __aenter__(
        self,
    ) -> DummyStreamResponse:  # pragma: no cover - context stub
        return self

    async def __aexit__(
        self, exc_type, exc, tb
    ) -> None:  # pragma: no cover - context stub
        return None

    def aiter_lines(self) -> AsyncGenerator[str, None]:
        async def _gen() -> AsyncGenerator[str, None]:
            for item in self._lines:
                if isinstance(item, float):
                    await asyncio.sleep(item)
                    yield ""
                else:
                    yield item

        return _gen()

    async def aread(self) -> bytes:
        return self._body


class MockAsyncClient:
    queue: list[Any] = []

    def __init__(
        self, *args: Any, **kwargs: Any
    ) -> None:  # pragma: no cover - init stub
        pass

    async def __aenter__(self) -> MockAsyncClient:  # pragma: no cover - context stub
        return self

    async def __aexit__(
        self, exc_type, exc, tb
    ) -> None:  # pragma: no cover - context stub
        return None

    def stream(
        self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]
    ) -> DummyStreamResponse:
        if not self.queue:
            raise AssertionError("MockAsyncClient queue exhausted")
        response = self.queue.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    monkeypatch.delenv("FLUIDRAG_OFFLINE", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_HTTP_REFERER", raising=False)
    monkeypatch.delenv("OPENROUTER_APP_TITLE", raising=False)


@pytest.fixture(autouse=True)
def _patch_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "_sleep", lambda delay: None)

    async def _noop(delay: float) -> None:
        return None

    monkeypatch.setattr(client_module, "_async_sleep", _noop)


@pytest.fixture()
def online_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLUIDRAG_OFFLINE", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "https://example.com")
    monkeypatch.setenv("OPENROUTER_APP_TITLE", "FluidRAG Tests")
    get_settings.cache_clear()


def test_chat_sync_offline_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLUIDRAG_OFFLINE", "true")
    get_settings.cache_clear()
    with pytest.raises(OpenRouterHTTPError):
        chat_sync("gpt", [{"role": "user", "content": "hi"}])


def test_chat_sync_retries_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, online_env
) -> None:
    monkeypatch.setattr(client_module.httpx, "Client", MockClient)
    MockClient.queue = [
        DummyResponse(429, {"error": {"message": "retry"}}),
        DummyResponse(200, {"id": "ok", "choices": []}),
    ]
    result = chat_sync("gpt", [{"role": "user", "content": "hello"}], retries=1)
    assert result["id"] == "ok"


def test_chat_stream_async_yields_events(
    monkeypatch: pytest.MonkeyPatch, online_env
) -> None:
    monkeypatch.setattr(client_module.httpx, "AsyncClient", MockAsyncClient)
    MockAsyncClient.queue = [
        DummyStreamResponse(
            200,
            [
                'data: {"delta": {"content": "hi"}}',
                "data: [DONE]",
            ],
        )
    ]

    async def _collect() -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        async for chunk in chat_stream_async(
            "gpt", [{"role": "user", "content": "hi"}], retries=0
        ):
            events.append(chunk)
        return events

    events = asyncio.run(_collect())
    assert events[0]["type"] == "delta"
    assert events[0]["data"]["delta"]["content"] == "hi"
    assert events[-1]["type"] == "done"


def test_chat_stream_idle_timeout(monkeypatch: pytest.MonkeyPatch, online_env) -> None:
    monkeypatch.setattr(client_module.httpx, "AsyncClient", MockAsyncClient)
    MockAsyncClient.queue = [DummyStreamResponse(200, [0.05])]

    async def _consume() -> None:
        async for _ in chat_stream_async(
            "gpt",
            [{"role": "user", "content": "hi"}],
            retries=0,
            idle_timeout=0.01,
        ):
            pass

    with pytest.raises(OpenRouterStreamError):
        asyncio.run(_consume())


def test_embed_sync_parses_vectors(monkeypatch: pytest.MonkeyPatch, online_env) -> None:
    monkeypatch.setattr(client_module.httpx, "Client", MockClient)
    MockClient.queue = [
        DummyResponse(200, {"data": [{"embedding": [1, 2, 3]}]}),
    ]
    result = embed_sync("text-embed", ["a", "b"], retries=0)
    assert result == [[1.0, 2.0, 3.0]]


def test_chat_sync_propagates_auth_error(
    monkeypatch: pytest.MonkeyPatch, online_env
) -> None:
    monkeypatch.setattr(client_module.httpx, "Client", MockClient)
    MockClient.queue = [DummyResponse(401, {"error": {"message": "bad key"}})]
    with pytest.raises(OpenRouterAuthError):
        chat_sync("gpt", [{"role": "user", "content": "hi"}], retries=0)
