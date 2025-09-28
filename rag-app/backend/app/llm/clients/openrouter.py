"""HTTP client for OpenRouter."""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncGenerator, Dict, Iterable, List

import httpx

from backend.app.config import settings
from backend.app.util.logging import get_logger
from backend.app.llm.utils.envsafe import openrouter_headers

logger = get_logger(__name__)


class OpenRouterError(RuntimeError):
    pass


class OpenRouterAuthError(OpenRouterError):
    pass


class OpenRouterHTTPError(OpenRouterError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenRouterStreamError(OpenRouterError):
    pass


def _backoff(retries: int, base: float = 0.5) -> Iterable[float]:
    for attempt in range(retries):
        yield base * (2 ** attempt)


def _request_headers() -> Dict[str, str]:
    headers = openrouter_headers(settings.openrouter_api_key)
    headers.setdefault("Content-Type", "application/json")
    return headers


def chat_sync(*, model: str, messages: List[Dict[str, str]], timeout: float = 60.0, retries: int = 3, **kwargs: Any) -> Dict[str, Any]:
    url = f"{settings.openrouter_base_url}/chat/completions"
    payload = {"model": model, "messages": messages, **kwargs}
    last_exc: Exception | None = None
    for delay in list(_backoff(retries)) + [None]:
        try:
            with httpx.Client(timeout=timeout) as http_client:
                resp = http_client.post(url, json=payload, headers=_request_headers())
            if resp.status_code == 401:
                raise OpenRouterAuthError("Invalid OpenRouter credentials")
            if resp.status_code >= 400:
                raise OpenRouterHTTPError(resp.status_code, resp.text)
            return resp.json()
        except (httpx.RequestError, OpenRouterHTTPError, OpenRouterAuthError) as exc:
            last_exc = exc
            if delay is None:
                break
            logger.warning("OpenRouter chat retry", extra={"delay": delay, "error": str(exc)})
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


async def chat_stream_async(
    *,
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 60.0,
    retries: int = 3,
    **kwargs: Any,
) -> AsyncGenerator[Dict[str, Any], None]:
    url = f"{settings.openrouter_base_url}/chat/completions"
    payload = {"model": model, "messages": messages, "stream": True, **kwargs}
    for delay in list(_backoff(retries)) + [None]:
        try:
            async with httpx.AsyncClient(timeout=timeout) as http_client:
                async with http_client.stream("POST", url, json=payload, headers=_request_headers()) as resp:
                    if resp.status_code == 401:
                        raise OpenRouterAuthError("Invalid OpenRouter credentials")
                    if resp.status_code >= 400:
                        raise OpenRouterHTTPError(resp.status_code, await resp.aread())
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        yield {"event": "delta", "data": line}
                    return
        except (httpx.RequestError, OpenRouterError) as exc:
            if delay is None:
                raise OpenRouterStreamError(str(exc)) from exc
            logger.warning("OpenRouter stream retry", extra={"delay": delay, "error": str(exc)})
            await asyncio.sleep(delay)


def embed_sync(*, model: str, inputs: List[str], timeout: float = 60.0, retries: int = 3) -> List[List[float]]:
    url = f"{settings.openrouter_base_url}/embeddings"
    payload = {"model": model, "input": inputs}
    last_exc: Exception | None = None
    for delay in list(_backoff(retries)) + [None]:
        try:
            with httpx.Client(timeout=timeout) as http_client:
                resp = http_client.post(url, json=payload, headers=_request_headers())
            if resp.status_code == 401:
                raise OpenRouterAuthError("Invalid OpenRouter credentials")
            if resp.status_code >= 400:
                raise OpenRouterHTTPError(resp.status_code, resp.text)
            data = resp.json()
            return [item["embedding"] for item in data.get("data", [])]
        except (httpx.RequestError, OpenRouterError) as exc:
            last_exc = exc
            if delay is None:
                break
            logger.warning("OpenRouter embeddings retry", extra={"delay": delay, "error": str(exc)})
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
