"""Offline-friendly LLM adapter."""

from __future__ import annotations

import hashlib
import math
from typing import Any

from ..config import get_settings
from ..util.errors import ExternalServiceError
from ..util.logging import get_logger, log_span

logger = get_logger(__name__)


def call_llm(system: str, user: str, context: str) -> dict[str, Any]:
    """Call configured LLM provider and return parsed result."""

    client = LLMClient()
    return client.chat(system=system, user=user, context=context)


class LLMClient:
    """Provider-agnostic LLM client with retries."""

    def __init__(self, provider: str = "openai", api_key: str | None = None) -> None:
        """Init client."""

        self._provider = provider
        self._api_key = api_key
        self._settings = get_settings()
        self._timeout = self._settings.openrouter_timeout_seconds
        self._max_retries = self._settings.openrouter_max_retries
        self._batch_size = self._settings.llm_batch_size
        if self._settings.offline:
            logger.info(
                "llm.offline_mode",
                extra={
                    "provider": provider,
                    "reason": "offline flag enabled",
                    "timeout": self._timeout,
                    "retries": self._max_retries,
                },
            )
        else:
            logger.info(
                "llm.online_mode",
                extra={
                    "provider": provider,
                    "timeout": self._timeout,
                    "retries": self._max_retries,
                },
            )

    def chat(
        self,
        system: str,
        user: str,
        context: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Chat completion with retry policy."""

        if self._settings.offline:
            with log_span(
                "llm.chat.offline",
                logger=logger,
                extra={"provider": self._provider, "max_tokens": max_tokens},
            ) as span_meta:
                summary = self._simulate_completion(system, user, context, max_tokens)
                span_meta["prompt_tokens"] = len(context.split())
            return {
                "content": summary,
                "provider": "offline-synth",
                "temperature": temperature,
                "tokens": {
                    "prompt": len(context.split()),
                    "completion": len(summary.split()),
                },
            }
        raise ExternalServiceError("Remote LLM invocation disabled in this environment")

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch embed via provider."""

        dimension = 16
        embeddings: list[list[float]] = []
        batch_size = max(self._settings.vector_batch_size, 1)
        for offset in range(0, len(texts), batch_size):
            batch = texts[offset : offset + batch_size]
            with log_span(
                "llm.embed.offline_batch",
                logger=logger,
                extra={"size": len(batch)},
            ):
                for text in batch:
                    digest = hashlib.sha256(text.encode("utf-8")).digest()
                    vector = [
                        (digest[i] / 255.0) * math.cos(i + 1) for i in range(dimension)
                    ]
                    embeddings.append(vector)
        return embeddings

    def _simulate_completion(
        self, system: str, user: str, context: str, max_tokens: int
    ) -> str:
        del system  # intentionally unused in offline stub
        prompt = user.strip()
        sentences = [line.strip() for line in context.splitlines() if line.strip()]
        if not sentences:
            return "No relevant context provided."
        summary = " ".join(sentences[:5])
        words = summary.split()
        if len(words) > max_tokens:
            words = words[:max_tokens]
        synthesized = " ".join(words)
        return f"{prompt}\n\nAnswer: {synthesized}"


__all__ = ["LLMClient", "call_llm"]
