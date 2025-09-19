import os
import logging
import time
from typing import Optional

import httpx

log = logging.getLogger("FluidRAG.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_REFERER = "https://localhost/"
_DEFAULT_APP_TITLE = "FluidRAG"


def _env_setting(*keys: str, default: str) -> str:
    """Return the first non-empty environment variable among ``keys``."""

    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return default


OPENROUTER_HTTP_REFERER = _env_setting(
    "OPENROUTER_HTTP_REFERER",
    "OPENROUTER_SITE_URL",
    "HTTP_REFERER",
    default=_DEFAULT_REFERER,
)
OPENROUTER_APP_TITLE = _env_setting(
    "OPENROUTER_APP_TITLE",
    "OPENROUTER_X_TITLE",
    "X_TITLE",
    default=_DEFAULT_APP_TITLE,
)
LLAMACPP_URL = os.environ.get("LLAMACPP_URL", "http://localhost:8080/v1/chat/completions")


class LLMAuthError(RuntimeError):
    """Raised when an LLM endpoint reports an authorization failure."""

    def __init__(self, message: str):
        super().__init__(message)


class OpenRouterAuthError(LLMAuthError):
    """Compatibility alias for existing OpenRouter-specific handling."""


class BaseLLMClient:
    def __init__(self):
        self._debug_records = []

    def drain_debug_records(self):
        data = list(self._debug_records)
        self._debug_records.clear()
        return data




def _concat_old_style(system: Optional[str], user: str) -> str:
    """Return a single-string prompt where role and message are concatenated."""
    parts = []
    if system:
        parts.append(f"system: {system.strip()}")
    parts.append(f"user: {user.strip()}")
    return "\n\n".join(parts)

class OpenRouterClient(BaseLLMClient):
    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "").strip()
        self.http_referer = OPENROUTER_HTTP_REFERER
        self.app_title = OPENROUTER_APP_TITLE

        self._auth_error_message: Optional[str] = None
        if not self.api_key:
            log.warning("[llm] OPENROUTER_API_KEY not set; returning mock outputs")

    def drain_debug_records(self):
        data = list(self._debug_records)
        self._debug_records.clear()
        return data

    async def acomplete(self, model: str, system: Optional[str], user: str, **kwargs) -> str:
        prompt = _concat_old_style(system, user)
        timestamp = time.time()
        base_record = {
            "model": model,
            "timestamp": timestamp,
            "request": {
                "url": OPENROUTER_URL,
                "prompt": prompt,
            }
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", 512)
        }
        headers_log = {
            "HTTP-Referer": self.http_referer,
            "X-Title": self.app_title,
        }
        if self._auth_error_message:
            record = dict(base_record)
            record["request"].update({
                "headers": {**headers_log, "Authorization": "*** (cached failure)"},
                "payload": payload
            })
            record["response"] = {
                "status": 401,
                "error": self._auth_error_message,
                "cached": True
            }
            self._debug_records.append(record)
            raise OpenRouterAuthError(self._auth_error_message)
        if not self.api_key:
            record = dict(base_record)
            record["request"].update({
                "headers": {**headers_log, "Authorization": "(missing)"},
                "payload": payload
            })
            record["response"] = {"mock": True, "body": "[]"}
            self._debug_records.append(record)
            return '[]'  # mock JSON for offline

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": self.http_referer,
            "X-Title": self.app_title,
        }
        timeout = httpx.Timeout(60.0, connect=20.0)
        headers_log = {**headers_log, "Authorization": "***"}
        record = dict(base_record)
        record["request"].update({
            "headers": headers_log,
            "payload": payload
        })
        try:
            async with httpx.AsyncClient(timeout=timeout, http2=True) as client:

                r = await client.post(OPENROUTER_URL, headers=headers, json=payload)
                status = r.status_code
                r.raise_for_status()
                data = r.json()
                content = data["choices"][0]["message"]["content"]
                record["response"] = {
                    "status": status,
                    "body": data,
                    "content": content
                }
                return content or ""
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response else None
            body_text: Optional[str] = None
            try:
                body_text = exc.response.text
            except Exception:  # pragma: no cover - defensive
                body_text = None
            record["response"] = {
                "status": status,
                "error": str(exc),
                "body_text": body_text
            }
            if status == 401:
                message = (
                    "OpenRouter rejected the request (401 Unauthorized). "
                    "Confirm that OPENROUTER_API_KEY is set to a valid key "
                    "with access to the selected model."
                )
                self._auth_error_message = message
                log.error("[llm] %s", message)
                raise OpenRouterAuthError(message) from exc
            log.exception("[llm] HTTP error from OpenRouter")
            raise
        except Exception as exc:
            record["response"] = {
                "status": None,
                "error": str(exc)
            }
            log.exception("[llm] request failed")
            raise
        finally:
            self._debug_records.append(record)



class LlamaCppClient(BaseLLMClient):
    """Client for llama.cpp servers that expose an OpenAI-compatible API."""

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        super().__init__()
        self.base_url = (base_url or LLAMACPP_URL).rstrip("/")
        self.api_key = api_key or os.environ.get("LLAMACPP_API_KEY", "").strip()
        self._auth_error_message: Optional[str] = None

    async def acomplete(self, model: str, system: Optional[str], user: str, **kwargs) -> str:
        prompt = _concat_old_style(system, user)
        timestamp = time.time()
        base_record = {
            "model": model,
            "timestamp": timestamp,
            "request": {
                "url": self.base_url,
                "prompt": prompt,
            }
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system or ""},
                {"role": "user", "content": user}
            ],
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", 512)
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        record = dict(base_record)
        log_headers = dict(headers)
        if "Authorization" in log_headers:
            log_headers["Authorization"] = "***"
        record["request"].update({
            "headers": log_headers,
            "payload": payload
        })

        if self._auth_error_message:

            record["response"] = {
                "status": 401,
                "error": self._auth_error_message,
                "cached": True
            }
            self._debug_records.append(record)
            raise LLMAuthError(self._auth_error_message)

        timeout = httpx.Timeout(60.0, connect=20.0)
        try:
            async with httpx.AsyncClient(timeout=timeout, http2=True) as client:

                r = await client.post(self.base_url, headers=headers, json=payload)
                status = r.status_code
                r.raise_for_status()
                data = r.json()
                message = data.get("choices", [{}])[0]
                content = (
                    message.get("message", {}).get("content")
                    if isinstance(message.get("message"), dict)
                    else message.get("text", "")
                )

                record["response"] = {
                    "status": status,
                    "body": data,
                    "content": content
                }
                return content or ""
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response else None
            body_text: Optional[str] = None
            try:
                body_text = exc.response.text
            except Exception:
                body_text = None
            record["response"] = {
                "status": status,
                "error": str(exc),
                "body_text": body_text
            }
            if status in (401, 403):
                message = (
                    "The llama.cpp endpoint rejected the request (authorization failure). "
                    "Confirm that the server is running and credentials (if any) are correct."
                )
                self._auth_error_message = message
                log.error("[llm] %s", message)
                raise LLMAuthError(message) from exc
            log.exception("[llm] HTTP error from llama.cpp endpoint")
            raise
        except Exception as exc:
            record["response"] = {
                "status": None,
                "error": str(exc)
            }
            log.exception("[llm] llama.cpp request failed")
            raise
        finally:
            self._debug_records.append(record)



def create_llm_client(provider: str) -> BaseLLMClient:
    normalized = (provider or "openrouter").strip().lower()
    if normalized == "llamacpp":
        return LlamaCppClient()
    return OpenRouterClient()


def provider_default_model(provider: str) -> Optional[str]:
    normalized = (provider or "openrouter").strip().lower()
    if normalized == "llamacpp":
        return os.environ.get("LLAMACPP_DEFAULT_MODEL")
    return None

