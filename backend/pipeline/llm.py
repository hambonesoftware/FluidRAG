import os
import logging
import time
from typing import Optional
import httpx

log = logging.getLogger("FluidRAG.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterAuthError(RuntimeError):
    """Raised when OpenRouter returns an authorization failure."""

    def __init__(self, message: str):
        super().__init__(message)


def _concat_old_style(system: Optional[str], user: str) -> str:
    """Return a single-string prompt where role and message are concatenated."""
    parts = []
    if system:
        parts.append(f"system: {system.strip()}")
    parts.append(f"user: {user.strip()}")
    return "\n\n".join(parts)

class OpenRouterClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "").strip()
        self._debug_records = []
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
            "HTTP-Referer": "https://localhost/",
            "X-Title": "FluidRAG"
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
            "HTTP-Referer": "https://localhost/",
            "X-Title": "FluidRAG"
        }
        timeout = httpx.Timeout(60.0, connect=20.0)
        headers_log = {**headers_log, "Authorization": "***"}
        record = dict(base_record)
        record["request"].update({
            "headers": headers_log,
            "payload": payload
        })
        async with httpx.AsyncClient(timeout=timeout, http2=True) as client:
            try:
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
