import os
import logging
from typing import Optional, Dict, Any
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
        if not self.api_key:
            log.warning("[llm] OPENROUTER_API_KEY not set; returning mock outputs")

    async def acomplete(self, model: str, system: Optional[str], user: str, **kwargs) -> str:
        prompt = _concat_old_style(system, user)
        if not self.api_key:
            return '[]'  # mock JSON for offline

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://localhost/",
            "X-Title": "FluidRAG"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", 512)
        }
        timeout = httpx.Timeout(60.0, connect=20.0)
        async with httpx.AsyncClient(timeout=timeout, http2=True) as client:
            r = await client.post(OPENROUTER_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            return content or ""
