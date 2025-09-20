from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

from ..errors import LLMAuthError
from ..utils import log_prompt, LLAMACPP_DEFAULT_URL
from .base import BaseLLMClient

log = logging.getLogger("FluidRAG.llm.llamacpp")

class LlamaCppClient(BaseLLMClient):
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, timeout_s: float = 60.0) -> None:
        super().__init__()
        self.base_url = (base_url or os.environ.get("LLAMACPP_URL", LLAMACPP_DEFAULT_URL)).rstrip("/")
        self.api_key = (api_key or os.environ.get("LLAMACPP_API_KEY", "")).strip()
        self._timeout = httpx.Timeout(timeout_s, connect=20.0)
        self._auth_error_message: Optional[str] = None

    async def acomplete(
        self,
        *,
        model: str,
        system: Optional[str],
        user: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        messages = []
        if system is not None:
            messages.append({"role": "system", "content": system or ""})
        messages.append({"role": "user", "content": user})

        payload: Dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        if extra:
            payload.update(extra)

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        record = {
            "provider": "llamacpp",
            "request": {"url": self.base_url, "headers": {**headers, "Authorization": "Bearer ***" if "Authorization" in headers else None}, "payload": payload, "prompt": log_prompt(messages)},
        }

        if self._auth_error_message:
            record["response"] = {"status": 401, "error": self._auth_error_message, "cached": True}
            self._push_debug(record)
            raise LLMAuthError(self._auth_error_message)

        try:
            async with httpx.AsyncClient(timeout=self._timeout, http2=True) as client:
                resp = await client.post(self.base_url, headers=headers, json=payload)
                status = resp.status_code
                body = resp.json()
                resp.raise_for_status()

                choice = body.get("choices", [{}])[0]
                content = ((choice.get("message") or {}).get("content", "") if isinstance(choice.get("message"), dict) else choice.get("text", "")) or ""
                record["response"] = {"status": status, "body": body, "content": content}
                self._push_debug(record)
                return content
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response else None
            text = None
            try:
                text = e.response.text
            except Exception:
                pass
            record["response"] = {"status": status, "error": str(e), "text": text}
            self._push_debug(record)
            if status in (401, 403):
                raise LLMAuthError("llama.cpp authorization failure") from e
            raise
        except Exception as e:
            record["response"] = {"status": None, "error": str(e)}
            self._push_debug(record)
            raise
