"""OpenRouter client supporting sync calls, streaming, and embeddings."""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from collections.abc import AsyncGenerator, Iterable, Mapping
from typing import Any

import httpx

from ...config import get_settings
from ...util.logging import get_logger
from ..utils import log_prompt, windows_curl
from ..utils.envsafe import masked_headers, openrouter_headers

logger = get_logger(__name__)

_RETRY_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class OpenRouterError(Exception):
    """Base error."""


class OpenRouterAuthError(OpenRouterError):
    """401 error."""


class OpenRouterHTTPError(OpenRouterError):
    """HTTP status/transport error."""


class OpenRouterStreamError(OpenRouterError):
    """Streaming idle/format error."""


def _base_url() -> str:
    return os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")


def _ensure_online() -> None:
    if get_settings().offline:
        raise OpenRouterHTTPError(
            "OpenRouter client disabled while FLUIDRAG_OFFLINE is true."
        )


def _compose_payload(
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    top_p: float | None,
    max_tokens: int | None,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if extra:
        payload.update(extra)
    return payload


def _parse_error(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict) and data.get("error"):
            error_payload = data["error"]
            if isinstance(error_payload, Mapping):
                message = error_payload.get("message")
                return str(message) if message is not None else str(error_payload)
            return str(error_payload)
    except json.JSONDecodeError:
        pass
    return response.text


def _should_retry(status_code: int) -> bool:
    return status_code in _RETRY_STATUS or 500 <= status_code < 600


def _decorate_headers(headers: dict[str, str]) -> dict[str, str]:
    merged = {"Accept": "application/json"}
    merged.update(headers)
    return merged


def _sleep(delay: float) -> None:
    if delay > 0:
        time.sleep(delay)


async def _async_sleep(delay: float) -> None:
    if delay > 0:
        await asyncio.sleep(delay)


def _backoff(
    retries: int = 3, base: float = 0.5, max_delay: float = 8.0
) -> Iterable[float]:
    """Yield jittered backoff durations."""
    yield 0.0
    for attempt in range(1, retries + 1):
        cap = min(max_delay, base * (2 ** (attempt - 1)))
        jitter = random.random() * (cap / 2)
        yield min(max_delay, cap + jitter)


def _readable_body(body: Any) -> str:
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="ignore")
    return str(body)


def chat_sync(
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.0,
    top_p: float | None = None,
    max_tokens: int | None = None,
    extra: dict[str, Any] | None = None,
    timeout: float = 60.0,
    retries: int = 3,
) -> dict[str, Any]:
    """Sync chat with retries and masked logging."""
    _ensure_online()
    payload = _compose_payload(model, messages, temperature, top_p, max_tokens, extra)
    try:
        headers = _decorate_headers(openrouter_headers())
    except RuntimeError as exc:
        raise OpenRouterHTTPError(str(exc)) from exc
    url = f"{_base_url()}/chat/completions"
    last_error: Exception | None = None

    for delay in _backoff(retries):
        _sleep(delay)
        try:
            logger.info(
                "openrouter.chat_sync", extra=log_prompt("chat_sync", payload, headers)
            )
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, json=payload)
            if response.status_code == 401:
                raise OpenRouterAuthError(_parse_error(response))
            if _should_retry(response.status_code):
                last_error = OpenRouterHTTPError(
                    f"Retryable status {response.status_code}: {_parse_error(response)}"
                )
                continue
            if response.status_code >= 400:
                raise OpenRouterHTTPError(
                    f"OpenRouter error {response.status_code}: {_parse_error(response)}"
                )
            data = response.json()
            if not isinstance(data, dict):
                raise OpenRouterHTTPError("Unexpected OpenRouter response payload.")
            return data
        except OpenRouterAuthError:
            raise
        except httpx.HTTPError as exc:
            last_error = OpenRouterHTTPError(f"HTTP error: {exc}")
        except OpenRouterHTTPError as exc:
            last_error = exc
    if last_error:
        logger.error(
            "openrouter.chat_sync.failure",
            extra={
                "error": str(last_error),
                "curl": windows_curl(url, masked_headers(headers), payload),
            },
        )
        raise last_error
    raise OpenRouterHTTPError("OpenRouter chat failed without explicit error.")


async def _iterate_stream(
    response: httpx.Response, idle_timeout: float
) -> AsyncGenerator[dict[str, Any], None]:
    last_event = time.monotonic()
    event = "delta"
    async for raw in response.aiter_lines():
        if raw == "":
            if time.monotonic() - last_event > idle_timeout:
                raise OpenRouterStreamError(
                    f"Stream stalled for {idle_timeout:.1f}s without data."
                )
            continue
        if raw.startswith("event:"):
            event = raw.split(":", 1)[1].strip() or "delta"
            continue
        if not raw.startswith("data:"):
            continue
        data = raw.split(":", 1)[1].strip()
        if data == "[DONE]":
            yield {"type": "done"}
            return
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise OpenRouterStreamError("Malformed SSE payload.") from exc
        kind = "delta" if event in {"delta", "message"} else event
        yield {"type": kind, "data": parsed}
        last_event = time.monotonic()
        event = "delta"
    yield {"type": "done"}


async def chat_stream_async(
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.0,
    top_p: float | None = None,
    max_tokens: int | None = None,
    extra: dict[str, Any] | None = None,
    timeout: float = 60.0,
    retries: int = 3,
    idle_timeout: float = 30.0,
) -> AsyncGenerator[dict[str, Any], None]:
    """Async SSE streaming, yields deltas/meta/done."""
    _ensure_online()
    payload = _compose_payload(model, messages, temperature, top_p, max_tokens, extra)
    payload["stream"] = True
    try:
        headers = _decorate_headers(openrouter_headers())
    except RuntimeError as exc:
        raise OpenRouterHTTPError(str(exc)) from exc
    url = f"{_base_url()}/chat/completions"
    last_error: Exception | None = None

    for delay in _backoff(retries):
        await _async_sleep(delay)
        try:
            logger.info(
                "openrouter.chat_stream.start",
                extra=log_prompt("chat_stream", payload, headers),
            )
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", url, headers=headers, json=payload
                ) as response:
                    if response.status_code == 401:
                        raise OpenRouterAuthError(_parse_error(response))
                    if _should_retry(response.status_code):
                        body = await response.aread()
                        last_error = OpenRouterHTTPError(
                            f"Retryable status {response.status_code}: {_readable_body(body)}"
                        )
                        continue
                    if response.status_code >= 400:
                        body = await response.aread()
                        raise OpenRouterHTTPError(
                            f"OpenRouter error {response.status_code}: {_readable_body(body)}"
                        )
                    async for item in _iterate_stream(response, idle_timeout):
                        yield item
                    return
        except OpenRouterAuthError:
            raise
        except OpenRouterStreamError as exc:
            last_error = exc
        except httpx.HTTPError as exc:
            last_error = OpenRouterHTTPError(f"HTTP error: {exc}")
        except OpenRouterHTTPError as exc:
            last_error = exc
    if last_error:
        logger.error(
            "openrouter.chat_stream.failure",
            extra={"error": str(last_error), "headers": masked_headers(headers)},
        )
        raise last_error
    raise OpenRouterHTTPError("OpenRouter streaming failed without explicit error.")


def embed_sync(
    model: str,
    inputs: list[str],
    timeout: float = 60.0,
    retries: int = 3,
) -> list[list[float]]:
    """Sync embeddings with retries."""
    _ensure_online()
    try:
        headers = _decorate_headers(openrouter_headers())
    except RuntimeError as exc:
        raise OpenRouterHTTPError(str(exc)) from exc
    url = f"{_base_url()}/embeddings"
    payload = {"model": model, "input": inputs}
    last_error: Exception | None = None

    for delay in _backoff(retries):
        _sleep(delay)
        try:
            logger.info(
                "openrouter.embed_sync", extra={"model": model, "count": len(inputs)}
            )
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, json=payload)
            if response.status_code == 401:
                raise OpenRouterAuthError(_parse_error(response))
            if _should_retry(response.status_code):
                last_error = OpenRouterHTTPError(
                    f"Retryable status {response.status_code}: {_parse_error(response)}"
                )
                continue
            if response.status_code >= 400:
                raise OpenRouterHTTPError(
                    f"OpenRouter error {response.status_code}: {_parse_error(response)}"
                )
            body = response.json()
            if not isinstance(body, dict):
                raise OpenRouterHTTPError("Unexpected embeddings response payload.")
            data = body.get("data", [])
            embeddings: list[list[float]] = []
            for row in data:
                if not isinstance(row, Mapping):
                    continue
                embedding = row.get("embedding")
                if isinstance(embedding, list):
                    embeddings.append([float(val) for val in embedding])
            return embeddings
        except OpenRouterAuthError:
            raise
        except httpx.HTTPError as exc:
            last_error = OpenRouterHTTPError(f"HTTP error: {exc}")
        except OpenRouterHTTPError as exc:
            last_error = exc
    if last_error:
        logger.error(
            "openrouter.embed_sync.failure",
            extra={
                "error": str(last_error),
                "curl": windows_curl(url, masked_headers(headers), payload),
            },
        )
        raise last_error
    raise OpenRouterHTTPError("OpenRouter embeddings failed without explicit error.")


__all__ = [
    "OpenRouterError",
    "OpenRouterAuthError",
    "OpenRouterHTTPError",
    "OpenRouterStreamError",
    "_backoff",
    "chat_sync",
    "chat_stream_async",
    "embed_sync",
]
