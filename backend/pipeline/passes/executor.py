"""Execution primitives for running individual passes."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

import httpx


from backend.llm.clients.openrouter import call_openrouter_chat
from backend.llm.errors import LLMAuthError
from backend.llm.factory import create_llm_client
from backend.utils.strings import s

from .chunking import build_user_prompt
from .config import resolve_retry_config
from .responses import parse_pass_response

log = logging.getLogger("FluidRAG.passes")


async def execute_pass(
    pass_name: str,
    system_prompt: str,
    groups: List[Dict[str, Any]],
    provider: str,
    model: str,
    metadata: Dict[str, Any],
    timeout_s: float,
    *,
    req_id: str,
    debug_llm_io: bool,
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    """Run a single pass across all chunk groups."""

    client = create_llm_client(provider)
    pass_rows: List[Dict[str, str]] = []
    csv_segments: List[str] = []
    errors: List[Dict[str, Any]] = []
    batch_debug: List[Dict[str, Any]] = []

    base_req_id = s(req_id) or uuid.uuid4().hex[:8]
    req_id = base_req_id

    retry_config = resolve_retry_config()
    temperature = retry_config["temperature"]
    max_tokens = retry_config["max_tokens"]
    max_attempts = int(retry_config["max_attempts"])
    initial_backoff_ms = int(retry_config["initial_backoff_ms"])
    backoff_factor = float(retry_config["backoff_factor"])
    backoff_max_ms = int(retry_config["backoff_max_ms"])

    backoff_initial_s = max(0.1, initial_backoff_ms / 1000.0)
    backoff_ceiling_s = max(backoff_initial_s, backoff_max_ms / 1000.0)

    fatal_error = False

    for batch_index, group in enumerate(groups):
        prompt = build_user_prompt(metadata, group, batch_index, len(groups))
        log.debug(
            "[passes] pass=%s batch=%d/%d chunks=%d tokens≈%s",
            pass_name,
            batch_index + 1,
            len(groups),
            len(group.get("chunks", [])),
            group.get("token_estimate"),
        )
        backoff_s = backoff_initial_s
        attempts_used = 0
        content: Optional[str] = None
        response_meta: Optional[Dict[str, Any]] = None

        messages: List[Dict[str, Any]] = []
        if system_prompt is not None:
            messages.append({"role": "system", "content": system_prompt or ""})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)

        for attempt in range(1, max_attempts + 1):
            attempts_used = attempt

            try:
                log.info(
                    "[passes] req=%s pass=%s batch=%d/%d attempt=%d",
                    req_id,
                    pass_name,
                    batch_index + 1,
                    len(groups),
                    attempt,
                )

                if provider == "openrouter" and debug_llm_io:
                    call_req_id = f"{req_id}:{pass_name}:{batch_index + 1}:{attempt}"
                    call_result = await asyncio.wait_for(
                        call_openrouter_chat(dict(payload), req_id=call_req_id, debug_llm_io=True),
                        timeout=timeout_s,
                    )
                    if not call_result.get("ok", False):
                        status = call_result.get("http")
                        message = call_result.get("error") or "llm_call_failed"
                        if status == 429 and attempt < max_attempts:
                            await asyncio.sleep(backoff_s)
                            backoff_s = min(backoff_s * backoff_factor, backoff_ceiling_s)
                            continue
                        log.error(
                            "[passes] req=%s pass=%s batch=%d/%d attempt=%d error=%s http=%s",
                            req_id,
                            pass_name,
                            batch_index + 1,
                            len(groups),
                            attempt,
                            message,
                            status,
                        )
                        errors.append(
                            {
                                "batch": batch_index,
                                "error": message,
                                "pass": pass_name,
                                "model": model,
                                "provider": provider,
                                "req": req_id,
                                "http": status,
                            }
                        )
                        batch_debug.append(
                            {
                                "ok": False,
                                "pass": pass_name,
                                "batch": batch_index,
                                "attempts": attempts_used,
                                "error": message,
                                "req": req_id,
                                "http": status,
                            }
                        )
                        fatal_error = True
                        break
                    data = call_result.get("data") or {}
                    response_meta = call_result.get("meta")
                    choices = data.get("choices") or []
                    if choices:
                        content = choices[0].get("message", {}).get("content")
                    else:
                        content = ""
                else:
                    content = await asyncio.wait_for(
                        client.acomplete(
                            model=model,
                            system=system_prompt,
                            user=prompt,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            extra={"stream": True},
                        ),
                        timeout=timeout_s,
                    )

                break
            except asyncio.TimeoutError:
                error_msg = f"timeout after {timeout_s:.1f}s"
                log.error(
                    "[passes] req=%s pass=%s batch=%d timeout after %.1fs",
                    req_id,
                    pass_name,
                    batch_index + 1,
                    timeout_s,
                )
                errors.append(
                    {
                        "batch": batch_index,
                        "error": error_msg,
                        "pass": pass_name,
                        "timeout_s": timeout_s,
                        "model": model,
                        "provider": provider,
                        "req": req_id,
                    }
                )
                batch_debug.append(
                    {
                        "ok": False,
                        "pass": pass_name,
                        "batch": batch_index,
                        "attempts": attempts_used,
                        "error": error_msg,
                        "req": req_id,
                    }
                )
                fatal_error = True
                break
            except LLMAuthError as exc:
                msg = str(exc)
                log.error("[passes] req=%s pass=%s auth error: %s", req_id, pass_name, msg)
                errors.append(
                    {
                        "batch": batch_index,
                        "error": msg,
                        "pass": pass_name,
                        "model": model,
                        "provider": provider,
                        "req": req_id,
                    }
                )
                batch_debug.append(
                    {
                        "ok": False,
                        "pass": pass_name,
                        "batch": batch_index,
                        "attempts": attempts_used,
                        "error": msg,
                        "req": req_id,
                    }
                )
                fatal_error = True
                break
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response else None
                message = f"HTTP {status}: {exc}"
                if status == 429 and attempt < max_attempts:
                    await asyncio.sleep(backoff_s)
                    backoff_s = min(backoff_s * backoff_factor, backoff_ceiling_s)
                    continue
                log.error(
                    "[passes] req=%s pass=%s batch=%d transport error: %s",
                    req_id,
                    pass_name,
                    batch_index + 1,
                    message,
                )
                errors.append(
                    {
                        "batch": batch_index,
                        "error": message,
                        "pass": pass_name,
                        "model": model,
                        "provider": provider,
                        "req": req_id,
                    }
                )
                batch_debug.append(
                    {
                        "ok": False,
                        "pass": pass_name,
                        "batch": batch_index,
                        "attempts": attempts_used,
                        "error": message,
                        "req": req_id,
                    }
                )
                fatal_error = True
                break
            except Exception as exc:  # pragma: no cover - defensive
                message = str(exc)
                retryable = attempt < max_attempts and (
                    "429" in message or "Too Many Requests" in message
                )
                if retryable:
                    await asyncio.sleep(backoff_s)
                    backoff_s = min(backoff_s * backoff_factor, backoff_ceiling_s)
                    continue
                log.exception(
                    "[passes] req=%s pass=%s batch=%d exception",
                    req_id,
                    pass_name,
                    batch_index + 1,
                )
                errors.append(
                    {
                        "batch": batch_index,
                        "error": message,
                        "pass": pass_name,
                        "model": model,
                        "provider": provider,
                        "req": req_id,
                    }
                )
                batch_debug.append(
                    {
                        "ok": False,
                        "pass": pass_name,
                        "batch": batch_index,
                        "attempts": attempts_used,
                        "error": message,
                        "req": req_id,
                    }
                )
                fatal_error = True
                break

        if fatal_error:
            break

        if content is None:
            continue

        rows, csv_block, _json_block = parse_pass_response(content, pass_name)
        if rows:
            pass_rows.extend(rows)
        if csv_block:
            csv_segments.append(csv_block)
        if response_meta is not None and batch_debug:
            batch_debug[-1].setdefault("meta", response_meta)

    debug_records = client.drain_debug_records()
    debug_records.extend(batch_debug)
    for record in debug_records:
        record.setdefault("pass", pass_name)
        record.setdefault("model", model)

    if errors:
        for record in debug_records:
            record.setdefault("errors", []).extend(errors)
    return pass_rows, debug_records, csv_segments, errors
