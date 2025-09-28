"""LLM adapter built on the OpenRouter client."""
from __future__ import annotations

from typing import Any, Dict, List

from ..config import settings
from ..llm import openrouter
from ..util.logging import get_logger

logger = get_logger(__name__)


def call_llm(messages: List[Dict[str, str]], *, model: str = "openai/gpt-3.5-turbo") -> Dict[str, Any]:
    client = LLMClient()
    return client.chat(model=model, messages=messages)


class LLMClient:
    def __init__(self) -> None:
        self.base_url = settings.openrouter_base_url

    def chat(self, *, model: str, messages: List[Dict[str, str]], **kwargs: Any) -> Dict[str, Any]:
        if not settings.openrouter_api_key:
            logger.warning("OPENROUTER_API_KEY not configured; returning deterministic stub")
            joined = "\n".join(msg.get("content", "") for msg in messages)
            return {"model": model, "choices": [{"message": {"role": "assistant", "content": joined[::-1]}}]}
        return openrouter.chat(model=model, messages=messages, **kwargs)

    def embed(self, *, model: str, inputs: List[str]) -> List[List[float]]:
        if not settings.openrouter_api_key:
            logger.warning("OPENROUTER_API_KEY not configured; using hash embeddings")
            from .vectors import EmbeddingModel

            return EmbeddingModel().embed_texts(inputs)
        from ..llm.clients import openrouter as client

        return client.embed_sync(model=model, inputs=inputs)
