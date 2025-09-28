"""OpenRouter HTTP client implementations."""
from __future__ import annotations

import asyncio
import json
import random
from typing import Any, AsyncGenerator, Dict, Iterable, Iterator, List

import httpx

from backend.app.config import settings
from backend.app.llm.utils import log_prompt
from backend.app.llm.utils.envsafe import openrouter_headers
from backend.app.util.logging import get_logger
from backend.app.util.retry import RetryPolicy, with_retries

logger = get_logger(__name__)


class OpenRouterError(Exception):
    """Base error."""


class OpenRouterAuthError(OpenRouterError):
    """401 error."""


class OpenRouterHTTPError(OpenRouterError):
    """HTTP status/transport error."""


class OpenRouterStreamError(OpenRouterError):
    """Streaming idle/format error."""


def _backoff(retries: int = 3, base: float = 0.5, max_delay: float = 8.0) -> Iterable[float]:
    """Yield jittered backoff durations."""

    delay = base
    for _ in range(max(0, retries)):
        jitter = random.uniform(0.75, 1.25)
        yield min(max_delay, delay) * jitter
        delay *= 2


def _post_once(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    """Perform a single synchronous POST request."""

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:  # pragma: no cover - network dependent
        raise OpenRouterHTTPError("OpenRouter request timed out") from exc
    except httpx.HTTPError as exc:
        raise OpenRouterHTTPError(str(exc)) from exc

    if response.status_code == 401:
        raise OpenRouterAuthError("Unauthorized")
    if response.status_code >= 400:
        raise OpenRouterHTTPError(response.text)
    try:
        return response.json()
    except ValueError as exc:
        raise OpenRouterHTTPError("Invalid JSON response from OpenRouter") from exc


def chat_sync(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.0,
    top_p: float | None = None,
    max_tokens: int | None = None,
    extra: Dict[str, Any] | None = None,
    timeout: float = 60.0,
    retries: int = 3,
) -> Dict[str, Any]:
    """Sync chat with retries and masked logging."""

    payload: Dict[str, Any] = {
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

    headers = openrouter_headers()
    logger.info("openrouter_chat_sync", extra=log_prompt("sync", payload, headers))
    url = f"{settings.openrouter_base_url}/chat/completions"

    policy = RetryPolicy(retries=retries, base_delay=0.5, max_delay=8.0)
    return with_retries(
        lambda: _post_once(url, headers, payload, timeout),
        (OpenRouterHTTPError,),
        policy=policy,
    )


async def _stream_once(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    timeout: float,
    idle_timeout: float,
) -> AsyncGenerator[Dict[str, Any], None]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            if response.status_code == 401:
                raise OpenRouterAuthError("Unauthorized")
            if response.status_code >= 400:
                body = await response.aread()
                raise OpenRouterHTTPError(body.decode("utf-8", errors="ignore"))

            iterator = response.aiter_raw()
            buffer = b""

            while True:
                try:
                    chunk = await asyncio.wait_for(iterator.__anext__(), timeout=idle_timeout)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError as exc:
                    raise OpenRouterStreamError("OpenRouter stream idle timeout") from exc

                if not chunk:
                    continue

                buffer += chunk
                while b"\n\n" in buffer:
                    event_bytes, buffer = buffer.split(b"\n\n", 1)
                    event_text = event_bytes.decode("utf-8", errors="ignore").strip()
                    if not event_text:
                        continue
                    if not event_text.startswith("data:"):
                        logger.debug("openrouter_stream_skip", extra={"event": event_text})
                        continue
                    data = event_text[len("data:") :].strip()
                    if data == "[DONE]":
                        yield {"event": "done"}
                        return
                    try:
                        payload = json.loads(data)
                    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                        raise OpenRouterStreamError("Invalid JSON chunk") from exc
                    yield {"event": "delta", "data": payload}

            if buffer:
                logger.debug("openrouter_stream_buffer", extra={"buffer": buffer.decode(errors="ignore")})


async def chat_stream_async(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.0,
    top_p: float | None = None,
    max_tokens: int | None = None,
    extra: Dict[str, Any] | None = None,
    timeout: float = 60.0,
    retries: int = 3,
    idle_timeout: float = 30.0,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Async SSE streaming, yields deltas/meta/done."""

    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if extra:
        payload.update(extra)

    headers = openrouter_headers()
    logger.info("openrouter_chat_stream", extra=log_prompt("stream", payload, headers))
    url = f"{settings.openrouter_base_url}/chat/completions"

    delays: Iterator[float] = iter(_backoff(retries=retries))
    attempt = 0
    while True:
        attempt += 1
        try:
            async for event in _stream_once(url, headers, payload, timeout, idle_timeout):
                yield event
            return
        except (OpenRouterHTTPError, OpenRouterStreamError, httpx.HTTPError) as exc:
            logger.warning(
                "openrouter_stream_retry",
                extra={"attempt": attempt, "error": str(exc)},
            )
            try:
                delay = next(delays)
            except StopIteration:
                raise OpenRouterHTTPError(str(exc)) from exc
            await asyncio.sleep(delay)


def embed_sync(
    model: str,
    inputs: List[str],
    timeout: float = 60.0,
    retries: int = 3,
) -> List[List[float]]:
    """Sync embeddings with retries."""

    payload: Dict[str, Any] = {"model": model, "input": inputs}
    headers = openrouter_headers()
    url = f"{settings.openrouter_base_url}/embeddings"
    logger.info("openrouter_embed", extra=log_prompt("embed", payload, headers))

    policy = RetryPolicy(retries=retries, base_delay=0.5, max_delay=8.0)

    def _embed_once() -> List[List[float]]:
        response = _post_once(url, headers, payload, timeout)
        vectors = [item["embedding"] for item in response.get("data", [])]
        if not vectors:
            logger.warning("openrouter_embed_empty")
        return vectors

    return with_retries(_embed_once, (OpenRouterHTTPError,), policy=policy)
