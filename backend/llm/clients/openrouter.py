# backend/llm/clients/openrouter.py
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import uuid
from typing import Any, Dict, Optional

import certifi
import httpx

from ..errors import LLMAuthError, OpenRouterAuthError
from ..utils import (
    env_first,
    log_prompt,
    windows_curl,
    OPENROUTER_URL,
    DEFAULT_APP_TITLE,
    DEFAULT_REFERER,
)
from ...utils.envsafe import openrouter_headers
from .base import BaseLLMClient

log = logging.getLogger("FluidRAG.llm.openrouter")


class OpenRouterClient(BaseLLMClient):
    """
    OpenRouter chat client with robust transport + detailed, masked debug logging.

    - OpenAI-compatible /chat/completions payload.
    - Sends Authorization + (recommended) HTTP-Referer / X-Title headers.
    - Logs: correlation id, masked headers, payload meta, latency, error category, and repro cURL.
    - Transport hardening for Windows/proxy/AV environments (HTTP/1.1, certifi CA bundle, trust_env=False).
    - Gentle retries for transient 408/429/5xx responses.
    """

    def __init__(self, api_key: Optional[str] = None, timeout_s: float = 60.0) -> None:
        super().__init__()
        self.api_key = (api_key or os.environ.get("OPENROUTER_API_KEY", "")).strip()
        self.http_referer = (
            env_first("OPENROUTER_HTTP_REFERER", "OPENROUTER_SITE_URL", "HTTP_REFERER", default=DEFAULT_REFERER)
            or DEFAULT_REFERER
        )
        self.app_title = (
            env_first("OPENROUTER_APP_TITLE", "OPENROUTER_X_TITLE", "X_TITLE", default=DEFAULT_APP_TITLE)
            or DEFAULT_APP_TITLE
        )
        self._timeout = httpx.Timeout(timeout_s, connect=20.0)
        self._auth_error_message: Optional[str] = None

        if not self.api_key:
            log.warning("[llm] OPENROUTER_API_KEY not set; client will return mock content")

    async def acomplete(
        self,
        *,
        model: str,
        system: Optional[str],
        user: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        # Build messages
        messages = []
        if system is not None:
            messages.append({"role": "system", "content": system or ""})
        messages.append({"role": "user", "content": user})

        # Build payload (force non-streaming)
        stream = False
        payload: Dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        if extra:
            payload.update(extra)
            payload["stream"] = False

        # Headers
        auth_header = f"Bearer {self.api_key}" if self.api_key else ""
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "HTTP-Referer": self.http_referer,
            "X-Title": self.app_title,
        }

        # Masked headers for logs
        dbg_headers = dict(headers)
        if dbg_headers.get("Authorization"):
            dbg_headers["Authorization"] = "Bearer ***"

        # Correlation + timing
        cid = uuid.uuid4().hex[:8]
        t0 = time.time()

        # Prepare debug request record (keep original payload AND a summarized meta)
        request_debug = {
            "cid": cid,
            "url": OPENROUTER_URL,
            "headers": dbg_headers,
            "payload": payload,  # full payload (safe—no secrets inside)
            "payload_meta": {
                "model": model,
                "messages": len(messages),
                "stream": bool(stream),
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            "prompt": log_prompt(messages),
            "curl": windows_curl(
                OPENROUTER_URL,
                [
                    ("Authorization", "Bearer ***" if self.api_key else "(missing)"),
                    ("Content-Type", "application/json"),
                    ("HTTP-Referer", self.http_referer),
                    ("X-Title", self.app_title),
                ],
                payload,
            ),
        }
        record = {"provider": "openrouter", "request": request_debug}

        # Helper to finish and push the debug record
        def _finish(status: int, body: Optional[dict], content: Optional[str], err: Optional[str] = None):
            elapsed_ms = round((time.time() - t0) * 1000, 1)
            record["response"] = {
                "cid": cid,
                "status": status,
                "elapsed_ms": elapsed_ms,
                "error": err,
                "body_meta": (
                    {
                        "id": body.get("id"),
                        "model": body.get("model"),
                        "usage": body.get("usage"),
                    }
                    if isinstance(body, dict)
                    else None
                ),
                "content_preview": (content or "")[:160] if content else None,
            }
            self._push_debug(record)

        # Cached auth error (avoid spamming)
        if self._auth_error_message:
            _finish(401, None, None, f"auth_cached: {self._auth_error_message}")
            raise OpenRouterAuthError(self._auth_error_message)

        # Mock path (no API key)
        if not self.api_key:
            content = '{"status":"mock","provider":"openrouter"}'
            _finish(200, {"id": None, "model": model, "usage": None}, content, None)
            return content

        # ---- Real request with robust transport & retries ----
        retriable = {408, 409, 425, 429, 500, 502, 503, 504}
        attempts = 3

        async def _do_request() -> httpx.Response:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                http2=False,                 # more robust on Windows / corp proxies
                verify=certifi.where(),      # pin CA bundle
                trust_env=False,             # ignore proxy/env unless explicitly configured
            ) as client:
                log.info("[llm:%s] → POST %s stream=False", cid, OPENROUTER_URL)
                return await client.post(OPENROUTER_URL, headers=headers, json=payload)

        for i in range(1, attempts + 1):
            try:
                resp = await _do_request()
                status = resp.status_code
                raw_bytes = resp.content or b""
                if not raw_bytes:
                    try:
                        raw_bytes = await resp.aread()
                    except Exception:
                        raw_bytes = b""

                body_bytes = len(raw_bytes)
                gzipped = resp.headers.get("Content-Encoding", "").lower() == "gzip"
                log.info(
                    "[llm:%s] ← %s body-bytes=%d gzipped?=%s",
                    cid,
                    status,
                    body_bytes,
                    bool(gzipped),
                )

                text_body = raw_bytes.decode(resp.encoding or "utf-8", "replace") if raw_bytes else ""
                body: Optional[dict] = None
                if text_body:
                    try:
                        body = json.loads(text_body)
                    except json.JSONDecodeError:
                        preview = text_body[:1500]
                        log.warning("[llm:%s] non-JSON response preview=%r", cid, preview)
                        body = {"_raw_preview": preview}
                else:
                    body = {}

                if status >= 400:
                    err_label = f"http_{status}"
                    if status in retriable:
                        err_label = f"retriable_{status}_attempt_{i}"
                    _finish(status, body, None, err_label)
                    if status == 401:
                        msg = (
                            "OpenRouter rejected the request (401 Unauthorized). "
                            "Confirm that OPENROUTER_API_KEY is valid and that the selected model is allowed."
                        )
                        self._auth_error_message = msg
                        raise OpenRouterAuthError(msg)

                    if status in retriable and i < attempts:
                        wait = (0.4 * (2 ** (i - 1))) + random.uniform(0, 0.25)
                        await asyncio.sleep(wait)
                        continue

                    resp.raise_for_status()
                    continue

                # success path
                choice = (body or {}).get("choices", [{}])[0] if isinstance(body, dict) else {}
                content = (
                    choice.get("message", {}) if isinstance(choice, dict) else {}
                ).get("content", "")
                finish_reason = choice.get("finish_reason") if isinstance(choice, dict) else None
                usage = body.get("usage") if isinstance(body, dict) else None
                response_id = body.get("id") if isinstance(body, dict) else None
                log.info(
                    "[llm:%s] id=%s model=%s finish_reason=%s usage=%s",
                    cid,
                    response_id,
                    body.get("model") if isinstance(body, dict) else None,
                    finish_reason,
                    usage,
                )
                _finish(status, body, content, None)
                return content

            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response else 0

                # If we've already recorded the response for this CID, avoid duplicate logging.
                response_record = record.get("response") or {}
                if response_record.get("cid") == cid and response_record.get("status") == status:
                    if status == 401:
                        raise OpenRouterAuthError("Unauthorized") from e
                    if status in retriable and i < attempts:
                        wait = (0.4 * (2 ** (i - 1))) + random.uniform(0, 0.25)
                        await asyncio.sleep(wait)
                        continue
                    raise

                text_body: Optional[str] = None
                try:
                    raw = await e.response.aread()
                    text_body = raw.decode("utf-8", "replace")
                except Exception:
                    pass

                category = {
                    400: "bad_request",
                    401: "auth",
                    402: "credits",
                    403: "moderation",
                    408: "timeout",
                    429: "rate_limit",
                    502: "upstream",
                    503: "unavailable",
                    504: "gateway_timeout",
                }.get(status, "http_error")

                _finish(status, {"_text": text_body} if text_body else None, None, f"{category}: {str(e)}")

                if status == 401:
                    raise OpenRouterAuthError("Unauthorized") from e

                if status in retriable and i < attempts:
                    wait = (0.4 * (2 ** (i - 1))) + random.uniform(0, 0.25)
                    await asyncio.sleep(wait)
                    continue

                raise

            except Exception as e:
                # network/transport error; retry a couple times
                _finish(0, None, None, f"exception: {str(e)}")
                if i < attempts:
                    await asyncio.sleep(0.3 + random.uniform(0, 0.2))
                    continue
                raise

        # Should never hit here because we either returned or raised
        _finish(0, None, None, "unexpected_fallthrough")
        raise RuntimeError("OpenRouterClient: unexpected fallthrough in retry loop")


async def call_openrouter_chat(
    payload: Dict[str, Any], *, req_id: str, debug_llm_io: bool
) -> Dict[str, Any]:
    """Execute a chat completion with optional full payload/response logging."""

    rid = (req_id or "-").strip() or "-"
    headers = openrouter_headers()
    url = OPENROUTER_URL

    if debug_llm_io:
        try:
            safe_payload = json.loads(json.dumps(payload, ensure_ascii=False))
        except Exception:
            safe_payload = payload
        log.info(
            "[llm:%s] >>> OUTBOUND OpenRouter payload:\n%s",
            rid,
            json.dumps(safe_payload, ensure_ascii=False, indent=2),
        )

    timeout = httpx.Timeout(connect=20.0, read=360.0, write=60.0, pool=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=payload)

    text = response.text
    if debug_llm_io:
        log.info(
            "[llm:%s] <<< INBOUND OpenRouter raw response (status=%s):\n%s",
            rid,
            response.status_code,
            text,
        )

    result: Dict[str, Any] = {"ok": True, "http": response.status_code}
    if response.status_code >= 400:
        result["ok"] = False

    try:
        data = response.json()
    except Exception as exc:  # pragma: no cover - diagnostic path
        snippet = text.lstrip()[:300]
        log.error(
            "[llm:%s] JSON parse failed: %r\nFirst-non-ws: %r",
            rid,
            exc,
            snippet,
        )
        result.update({"error": "llm_non_json", "raw": text})
        return result

    meta = {
        "id": data.get("id"),
        "model": data.get("model"),
        "usage": data.get("usage"),
        "finish_reason": (data.get("choices") or [{}])[0].get("finish_reason"),
    }

    if not result["ok"] and "error" not in result:
        result["error"] = f"HTTP {response.status_code}"

    log.info("[llm:%s] meta=%s", rid, json.dumps(meta, ensure_ascii=False))

    result["data"] = data
    result["meta"] = meta
    result["raw"] = text
    return result
