import os
import logging
import time
from typing import Optional
import httpx

log = logging.getLogger("FluidRAG.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

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
            except Exception as exc:
                log.exception("[llm] request failed")
                record["response"] = {
                    "status": locals().get("status"),
                    "error": str(exc)
                }
                raise
            finally:
                self._debug_records.append(record)
