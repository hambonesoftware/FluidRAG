# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import base64
import csv
import io
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

from ..llm.errors import LLMAuthError
from ..llm.factory import create_llm_client, provider_default_model
from ..prompts import PASS_PROMPTS
from ..state import get_state
from ..utils.envsafe import env
from ..utils.strings import s

from .merge import merge_pass_outputs

from .fluid import fluid_refine_chunks
from .hep_cluster import hep_cluster_chunks

# Be resilient to missing helpers during upgrades
try:  # pragma: no cover - compatibility shim
    from .preprocess import (
        approximate_tokens,
        section_bounded_chunks_from_pdf,
    )
except Exception:  # pragma: no cover - compatibility shim
    def approximate_tokens(text: str) -> int:
        """Local fallback (~4 chars/token) if preprocess.approximate_tokens is unavailable."""

        if not text:
            return 0
        return max(1, len(text) // 4)


    def section_bounded_chunks_from_pdf(
        pdf_path: str,
        sidecar_dir: Optional[str] = None,
        tok_budget_chars: int = 6400,
        overlap_lines: int = 3,
        session_id: Optional[str] = None,
    ) -> Iterable[Dict[str, Any]]:
        raise RuntimeError("section_bounded_chunks_from_pdf unavailable")


log = logging.getLogger("FluidRAG.passes")


CHUNK_GROUP_TOKEN_LIMIT = 12000
DEFAULT_PASS_CONCURRENCY = 5
DEFAULT_PASS_TIMEOUT_S = 120
DEFAULT_PASS_TEMPERATURE = 0.0
DEFAULT_PASS_MAX_TOKENS = 4096
DEFAULT_PASS_MAX_ATTEMPTS = 4
DEFAULT_PASS_BACKOFF_INITIAL_MS = 600
DEFAULT_PASS_BACKOFF_FACTOR = 1.7
DEFAULT_PASS_BACKOFF_MAX_MS = 4500

CSV_COLUMNS = ["Document", "(Sub)Section #", "(Sub)Section Name", "Specification", "Pass"]

PASS_STAGGER_SECONDS = 5.0


def _snapshot(value: Any, limit: int = 3000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except Exception:
        text = repr(value)
    if len(text) > limit:
        truncated = len(text) - limit
        return f"{text[:limit]} … [truncated {truncated} chars]"
    return text


def _ensure_chunks(session_id: str) -> List[Dict[str, Any]]:
    state = get_state(session_id)
    if state is None:
        raise ValueError("Unknown session; upload and preprocess the document first.")

    if state.pre_chunks is not None and state.pre_chunks:
        chunks = [dict(chunk) for chunk in state.pre_chunks]
    else:
        pdf_path = state.file_path
        if not pdf_path or not os.path.exists(pdf_path):
            uploads_dir = os.getenv("UPLOAD_FOLDER", "uploads")
            pdf_path = os.path.join(uploads_dir, f"{session_id}.pdf")
        sidecar_dir = os.path.join("sidecars", session_id)
        chunks = [
            dict(chunk)
            for chunk in section_bounded_chunks_from_pdf(
                pdf_path,
                sidecar_dir=sidecar_dir,
                session_id=session_id,
            )
        ]

    document_name = state.filename or "Document"
    for chunk in chunks:
        chunk.setdefault("document", document_name)
        chunk.setdefault("section_number", chunk.get("section_id") or "")
        chunk.setdefault("section_name", chunk.get("section_title") or "")
        chunk.setdefault("page_start", chunk.get("page_start") or chunk.get("page") or 1)
        chunk.setdefault("page_end", chunk.get("page_end") or chunk.get("page") or chunk.get("page_start") or 1)
        chunk.setdefault("text", chunk.get("text", ""))
        chunk.setdefault("meta", {})

    refined = fluid_refine_chunks(chunks)
    enriched = hep_cluster_chunks(refined)
    state.refined_chunks = refined
    state.clustered_chunks = enriched
    return enriched


def _chunk_token_len(chunk: Dict[str, Any]) -> int:
    return approximate_tokens(chunk.get("text") or "")


def _build_groups(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    current_tokens = 0
    for chunk in chunks:
        tokens = max(1, _chunk_token_len(chunk))
        if current and current_tokens + tokens > CHUNK_GROUP_TOKEN_LIMIT:
            groups.append({
                "chunks": current,
                "token_estimate": current_tokens,
            })
            current = []
            current_tokens = 0
        current.append(chunk)
        current_tokens += tokens
    if current:
        groups.append({
            "chunks": current,
            "token_estimate": current_tokens,
        })
    return groups


def _format_chunk_for_prompt(chunk: Dict[str, Any], idx: int, total: int) -> str:
    doc = s(chunk.get("document")) or "Document"
    sec_num = s(chunk.get("section_number") or chunk.get("section_id"))
    sec_name = s(chunk.get("section_name") or chunk.get("section_title"))
    page_start = chunk.get("page_start") or chunk.get("page") or 1
    page_end = chunk.get("page_end") or page_start
    body = s(chunk.get("text"))
    header_bits = [f"Document: {doc}"]
    if sec_num or sec_name:
        section_label = " ".join(bit for bit in [sec_num, sec_name] if bit).strip()
        header_bits.append(f"Section: {section_label}")
    header_bits.append(f"Pages: {page_start}-{page_end}")
    header = " \u2022 ".join(header_bits)
    return f"<<<CHUNK {idx+1} OF {total}>>>\n{header}\n{body}\n<<<END CHUNK {idx+1}>>>"


def _build_user_prompt(metadata: Dict[str, Any], group: Dict[str, Any], batch_index: int, batch_total: int) -> str:
    chunk_texts = [
        _format_chunk_for_prompt(chunk, idx, len(group["chunks"]))
        for idx, chunk in enumerate(group["chunks"])
        if s(chunk.get("text"))
    ]
    document = metadata.get("document") or "Document"
    lines = [
        f"DOCUMENT_METADATA:\n- Document: {document}\n- Session: {metadata.get('session_id', '')}",
        f"BATCH_INFO: batch {batch_index + 1} of {batch_total}; approx {group.get('token_estimate', 0)} tokens",
        "DOCUMENT_TEXT:",
        "\n\n".join(chunk_texts) if chunk_texts else "(no text)",
        "Return results exactly as instructed in the system prompt. Do not omit CSV or JSON sections.",
    ]
    return "\n\n".join(lines).strip()


def _parse_pass_response(text: str, pass_name: str) -> Tuple[List[Dict[str, str]], Optional[str], Optional[str]]:
    if not text:
        return [], None, None
    csv_block: Optional[str] = None
    json_block: Optional[str] = None
    lower = text.lower()
    if "===csv===" in lower:
        split_csv = text.split("===CSV===", 1)[1]
    else:
        split_csv = text
    if "===JSON===" in split_csv:
        csv_part, json_part = split_csv.split("===JSON===", 1)
        csv_block = csv_part.strip()
        json_block = json_part.strip()
    else:
        csv_block = split_csv.strip()

    rows: List[Dict[str, str]] = []
    if csv_block:
        reader = csv.DictReader(io.StringIO(csv_block))
        for row in reader:
            if not any(row.values()):
                continue
            normalized = {col: s(row.get(col)) for col in CSV_COLUMNS}
            if not normalized["Pass"]:
                normalized["Pass"] = pass_name
            rows.append(normalized)
    return rows, csv_block, json_block


def _resolve_pass_concurrency(payload: Dict[str, Any]) -> int:
    source = (
        payload.get("max_parallel_passes")
        or payload.get("pass_concurrency")
        or env("LLM_PASS_CONCURRENCY")

        or DEFAULT_PASS_CONCURRENCY
    )
    try:
        value = int(source)
    except (TypeError, ValueError):
        return DEFAULT_PASS_CONCURRENCY
    return max(1, value)


def _resolve_pass_timeout(payload: Dict[str, Any]) -> float:
    source = (
        payload.get("pass_timeout_seconds")
        or env("LLM_PASS_TIMEOUT_SECONDS")

        or DEFAULT_PASS_TIMEOUT_S
    )
    try:
        value = float(source)
    except (TypeError, ValueError):
        return float(DEFAULT_PASS_TIMEOUT_S)
    return max(10.0, value)


def _int_from_env(name: str, default: int) -> int:
    try:
        value = int(env(name))
    except (TypeError, ValueError):
        return default
    return value


def _float_from_env(name: str, default: float) -> float:
    try:
        value = float(env(name))
    except (TypeError, ValueError):
        return default
    return value


async def _run_pass(
    pass_name: str,
    system_prompt: str,
    groups: List[Dict[str, Any]],
    provider: str,
    model: str,
    metadata: Dict[str, Any],
    timeout_s: float,
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    client = create_llm_client(provider)
    pass_rows: List[Dict[str, str]] = []
    csv_segments: List[str] = []
    errors: List[Dict[str, Any]] = []
    batch_debug: List[Dict[str, Any]] = []

    req_id = uuid.uuid4().hex[:8]
    temperature = _float_from_env("LLM_PASS_TEMPERATURE", DEFAULT_PASS_TEMPERATURE)
    max_tokens = _int_from_env("LLM_PASS_MAX_TOKENS", DEFAULT_PASS_MAX_TOKENS)
    max_attempts = max(1, _int_from_env("LLM_PASS_MAX_ATTEMPTS", DEFAULT_PASS_MAX_ATTEMPTS))
    initial_backoff_ms = _int_from_env(
        "LLM_PASS_BACKOFF_INITIAL_MS",
        _int_from_env("LLM_BACKOFF_INITIAL_MS", DEFAULT_PASS_BACKOFF_INITIAL_MS),
    )
    backoff_factor = _float_from_env(
        "LLM_PASS_BACKOFF_FACTOR",
        _float_from_env("LLM_BACKOFF_FACTOR", DEFAULT_PASS_BACKOFF_FACTOR),
    )
    backoff_max_ms = _int_from_env(
        "LLM_PASS_BACKOFF_MAX_MS",
        _int_from_env("LLM_BACKOFF_MAX_MS", DEFAULT_PASS_BACKOFF_MAX_MS),
    )

    backoff_initial_s = max(0.1, initial_backoff_ms / 1000.0)
    backoff_ceiling_s = max(backoff_initial_s, backoff_max_ms / 1000.0)

    fatal_error = False

    for batch_index, group in enumerate(groups):
        prompt = _build_user_prompt(metadata, group, batch_index, len(groups))
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
                content = await asyncio.wait_for(
                    client.acomplete(
                        model=model,
                        system=system_prompt,
                        user=prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        extra={"stream": False},
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
            except Exception as exc:
                message = str(exc)
                retryable = attempt < max_attempts and (
                    "429" in message or "Too Many Requests" in message
                )
                if retryable:
                    await asyncio.sleep(backoff_s)
                    backoff_s = min(backoff_s * backoff_factor, backoff_ceiling_s)
                    continue
                log.exception(
                    "[passes] req=%s pass=%s batch=%d exception", req_id, pass_name, batch_index + 1
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

        rows, csv_block, _json_block = _parse_pass_response(content, pass_name)
        if rows:
            pass_rows.extend(rows)
        if csv_block:
            csv_segments.append(csv_block)
        batch_debug.append(
            {
                "ok": True,
                "pass": pass_name,
                "batch": batch_index,
                "attempts": attempts_used,
                "req": req_id,
                "chunks": len(group.get("chunks", [])),
            }
        )

    debug_records = client.drain_debug_records()
    debug_records.extend(batch_debug)
    for record in debug_records:
        record.setdefault("pass", pass_name)
        record.setdefault("model", model)

    if errors:
        for record in debug_records:
            record.setdefault("errors", []).extend(errors)
    return pass_rows, debug_records, csv_segments, errors



def _encode_rows_to_csv(rows: List[Dict[str, str]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})
    return buffer.getvalue()


async def run_all_passes_async(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = payload or {}
    session_id = payload.get("session_id") or payload.get("session")
    if not session_id:
        return {"ok": False, "httpStatus": 400, "error": "session_id is required"}

    provider = s(payload.get("provider"))
    if not provider:
        provider = env("LLM_PROVIDER", "openrouter") or "openrouter"

    model = s(payload.get("model"))
    if not model:
        model = s(provider_default_model(provider))
    if not model:
        model = env("LLM_MODEL", "gpt-4o-mini") or "gpt-4o-mini"

    req_id = s(payload.get("req_id")) or uuid.uuid4().hex[:8]


    state = get_state(session_id)
    if state is None:
        return {"ok": False, "httpStatus": 404, "error": "Unknown session. Upload the document again."}

    state.provider = provider
    state.model = model

    try:
        chunks = _ensure_chunks(session_id)
    except Exception as exc:
        return {"ok": False, "httpStatus": 500, "error": f"Failed to prepare chunks: {exc}"}

    if not chunks:
        return {
            "ok": True,
            "rows": [],
            "csv_base64": None,
            "llm_debug": [],
            "metrics_ms": {"total": 0},
            "httpStatus": 200,
        }


    groups = _build_groups(chunks)
    metadata = {"document": state.filename or "Document", "session_id": session_id}

    debug_enabled = bool(payload.get("debug") or payload.get("_debug"))

    llm_debug: List[Dict[str, Any]] = []
    metrics: Dict[str, float] = {}
    all_errors: List[Dict[str, Any]] = []
    pass_outputs: Dict[str, Any] = {}

    pass_items = list(PASS_PROMPTS.items())
    requested_concurrency = _resolve_pass_concurrency(payload)
    pass_timeout = _resolve_pass_timeout(payload)

    concurrency_limit = max(1, min(requested_concurrency, len(pass_items)))
    log.info(
        "[passes] req=%s session=%s provider=%s model=%s passes=%d groups=%d concurrency=%d (requested=%d) timeout=%.1fs",
        req_id,
        session_id,
        provider,
        model,
        len(pass_items),
        len(groups),
        concurrency_limit,
        requested_concurrency,
        pass_timeout,
    )

    async def _execute_pass(pass_name: str, system_prompt: str):
        start = time.perf_counter()
        pass_rows, debug_records, pass_csv_segments, pass_errors = await _run_pass(

            pass_name,
            system_prompt,
            groups,
            provider,
            model,
            metadata,
            pass_timeout,
        )
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        return pass_name, pass_rows, debug_records, pass_csv_segments, elapsed_ms, pass_errors


    total_start = time.perf_counter()

    semaphore = asyncio.Semaphore(concurrency_limit)

    async def _bounded_execute(index: int, pass_name: str, system_prompt: str):
        if PASS_STAGGER_SECONDS > 0 and index > 0:
            delay = PASS_STAGGER_SECONDS * index
            log.debug(
                "[passes] delaying pass=%s by %.1fs before submission", pass_name, delay
            )
            await asyncio.sleep(delay)
        async with semaphore:
            return await _execute_pass(pass_name, system_prompt)

    tasks = [
        asyncio.create_task(_bounded_execute(idx, pass_name, system_prompt))
        for idx, (pass_name, system_prompt) in enumerate(pass_items)
    ]

    results: Dict[str, Tuple[List[Dict[str, str]], List[Dict[str, Any]], List[str], float, List[Dict[str, Any]]]] = {}
    for task in asyncio.as_completed(tasks):
        name, pass_rows, debug_records, pass_csv_segments, elapsed_ms, pass_errors = await task
        results[name] = (pass_rows, debug_records, pass_csv_segments, elapsed_ms, pass_errors)

    for pass_name, _system_prompt in pass_items:
        if pass_name not in results:
            continue
        pass_rows, debug_records, pass_csv_segments, elapsed_ms, pass_errors = results[pass_name]

        metrics[pass_name] = elapsed_ms
        llm_debug.extend(debug_records)
        all_errors.extend(pass_errors)
        payload_preview = {"items": pass_rows}
        pass_outputs[pass_name] = payload_preview
        log.info(
            "[passes %s] %s payload snapshot: %s",
            req_id,
            pass_name,
            _snapshot(payload_preview),
        )

    try:
        merged = merge_pass_outputs(pass_outputs, req_id=req_id)
    except Exception:
        log.exception("[passes %s] unhandled exception while constructing rows", req_id)
        return {
            "ok": False,
            "httpStatus": 500,
            "error": "merge_failed",
        }

    rows = merged.get("rows", [])
    merge_problems = merged.get("problems", [])

    metrics["total"] = round((time.perf_counter() - total_start) * 1000, 1)

    csv_text = _encode_rows_to_csv(rows)
    csv_base64 = base64.b64encode(csv_text.encode("utf-8")).decode("ascii") if rows else None

    response: Dict[str, Any] = {

        "ok": True,
        "rows": rows,
        "csv_base64": csv_base64,
        "csv_text": csv_text if rows else None,
        "llm_debug": llm_debug,
        "metrics_ms": metrics,
        "chunk_groups": len(groups),
        "chunk_count": len(chunks),
        "httpStatus": 200,
    }

    if debug_enabled:
        response.setdefault("debug", {})
        response["debug"]["merge"] = {
            "problems": merge_problems,
            "rows_count": len(rows),
        }

    if all_errors:
        first = all_errors[0]
        summary_bits = [first.get("error") or "pass failure"]
        if first.get("pass"):
            summary_bits.append(f"pass={first['pass']}")
        if first.get("batch") is not None:
            summary_bits.append(f"batch={first['batch']}")
        summary = " | ".join(summary_bits)
        response.update(
            {
                "ok": False,
                "httpStatus": 502,
                "error": f"One or more LLM passes failed: {summary}",
                "errors": all_errors,
            }
        )

    return response
