"""High level orchestration for running all passes."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Tuple

from backend.llm.factory import provider_default_model
from backend.persistence import get_pass_cache, save_pass_cache
from backend.state import get_state
from backend.utils.envsafe import env
from backend.utils.strings import s
from ..merge import merge_pass_outputs

from .chunking import build_groups, ensure_chunks, export_pass_stage_snapshots
from .config import (
    is_truthy_flag,
    resolve_pass_concurrency,
    resolve_pass_items,
    resolve_pass_timeout,
)
from .constants import ALL_PASSES, PASS_STAGGER_SECONDS
from .executor import execute_pass
from .responses import encode_rows_to_csv

log = logging.getLogger("FluidRAG.passes")


def _snapshot(value: Any, limit: int = 3000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False)
    except Exception:
        text = repr(value)
    if len(text) > limit:
        truncated = len(text) - limit
        return f"{text[:limit]} … [truncated {truncated} chars]"
    return text


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

    req_id = (
        s(payload.get("_req_id"))
        or s(payload.get("req_id"))
        or uuid.uuid4().hex[:8]
    )

    state = get_state(session_id)
    if state is None:
        return {"ok": False, "httpStatus": 404, "error": "Unknown session. Upload the document again."}

    state.provider = provider
    state.model = model

    try:
        chunks = ensure_chunks(session_id)
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "httpStatus": 500, "error": f"Failed to prepare chunks: {exc}"}

    try:
        export_pass_stage_snapshots(session_id, ALL_PASSES, include_header=True)
    except Exception:  # pragma: no cover - defensive
        log.exception("[passes %s] failed to export pass stage snapshots", req_id)

    if not chunks:
        return {
            "ok": True,
            "rows": [],
            "csv_base64": None,
            "llm_debug": [],
            "metrics_ms": {"total": 0},
            "httpStatus": 200,
        }

    groups = build_groups(chunks)
    metadata = {"document": state.filename or "Document", "session_id": session_id}

    debug_llm_io = bool(payload.get("_debug_llm_io") or payload.get("debug_llm_io"))

    llm_debug: List[Dict[str, Any]] = []
    metrics: Dict[str, float] = {}
    all_errors: List[Dict[str, Any]] = []
    pass_outputs: Dict[str, Any] = {}

    file_hash = getattr(state, "file_hash", None)

    pass_items, unknown_passes = resolve_pass_items(payload)
    if unknown_passes:
        log.warning(
            "[passes %s] ignoring unknown passes: %s",
            req_id,
            ", ".join(sorted({name for name in unknown_passes if name})),
        )
    if not pass_items:
        message = "No valid passes requested"
        if unknown_passes:
            message = (
                f"{message}; unknown passes: "
                f"{', '.join(sorted({name for name in unknown_passes if name}))}"
            )
        return {
            "ok": False,
            "httpStatus": 400,
            "error": message,
        }

    force_refresh = is_truthy_flag(payload.get("force_refresh"))

    if pass_items and any(name == "Mechanical" for name, _prompt in pass_items):
        first_mechanical = next(
            (item for item in pass_items if item[0] == "Mechanical"),
            None,
        )
        if first_mechanical is not None:
            remaining = [item for item in pass_items if item[0] != "Mechanical"]
            pass_items = [first_mechanical, *remaining]

    pass_offsets = {name: idx for idx, (name, _prompt) in enumerate(pass_items)}

    requested_concurrency = resolve_pass_concurrency(payload)

    pass_timeout = resolve_pass_timeout(payload)

    cached_pass_entries = get_pass_cache(file_hash) if file_hash else {}
    runnable_passes: List[Tuple[str, str]] = []
    cache_hits: List[str] = []
    cache_misses: List[str] = []

    for pass_name, system_prompt in pass_items:
        cached_entry = (
            cached_pass_entries.get(pass_name) if isinstance(cached_pass_entries, dict) else None
        )
        payload_preview = None
        stored_at = None
        cached_items: List[Dict[str, Any]] = []
        if isinstance(cached_entry, dict):
            payload_preview = cached_entry.get("payload")
            stored_at = cached_entry.get("stored_at")
        if isinstance(payload_preview, dict) and isinstance(payload_preview.get("items"), list):
            cached_items = [
                dict(item)
                for item in payload_preview.get("items", [])
                if isinstance(item, dict)
            ]

        has_cached_rows = bool(cached_items)
        use_cache = has_cached_rows and not force_refresh

        if use_cache:
            preview = {"items": cached_items}
            pass_outputs[pass_name] = preview
            metrics[pass_name] = 0.0
            cache_hits.append(pass_name)
            debug_entry: Dict[str, Any] = {
                "ok": True,
                "pass": pass_name,
                "batch": None,
                "attempts": 0,
                "req": req_id,
                "source": "cache",
                "model": model,
                "provider": provider,
            }
            if stored_at:
                debug_entry["cached_at"] = stored_at
            llm_debug.append(debug_entry)
            log.info(
                "[passes %s] %s payload snapshot (cache): %s",
                req_id,
                pass_name,
                _snapshot(preview),
            )
        else:
            runnable_passes.append((pass_name, system_prompt))
            cache_misses.append(pass_name)
            if has_cached_rows and force_refresh:
                log.info(
                    "[passes %s] %s cache bypassed due to force_refresh", req_id, pass_name
                )
            elif isinstance(payload_preview, dict) and not has_cached_rows:
                log.info(
                    "[passes %s] %s cache entry ignored (no cached rows)", req_id, pass_name
                )

    pending_count = len(runnable_passes)
    concurrency_limit = max(1, min(requested_concurrency, pending_count if pending_count else 1))
    log.info(
        "[passes] req=%s session=%s provider=%s model=%s passes=%d (execute=%d cached=%d) groups=%d concurrency=%d (requested=%d) timeout=%.1fs",
        req_id,
        session_id,
        provider,
        model,
        len(pass_items),
        pending_count,
        len(cache_hits),
        len(groups),
        concurrency_limit,
        requested_concurrency,
        pass_timeout,
    )

    async def _execute(pass_name: str, system_prompt: str):
        start = time.perf_counter()
        pass_rows, debug_records, pass_csv_segments, pass_errors = await execute_pass(
            pass_name,
            system_prompt,
            groups,
            provider,
            model,
            metadata,
            pass_timeout,
            req_id=req_id,
            debug_llm_io=debug_llm_io,
        )
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        return pass_name, pass_rows, debug_records, pass_csv_segments, elapsed_ms, pass_errors

    total_start = time.perf_counter()
    results: Dict[str, Tuple[List[Dict[str, str]], List[Dict[str, Any]], List[str], float, List[Dict[str, Any]]]] = {}

    if pending_count <= 1:
        for index, (pass_name, system_prompt) in enumerate(runnable_passes):
            position = pass_offsets.get(pass_name, index)
            if PASS_STAGGER_SECONDS > 0 and position > 0:
                delay = PASS_STAGGER_SECONDS * position
                log.debug(
                    "[passes] delaying pass=%s by %.1fs before submission", pass_name, delay
                )
                await asyncio.sleep(delay)

            start = time.perf_counter()
            pass_rows, debug_records, pass_csv_segments, pass_errors = await execute_pass(
                pass_name,
                system_prompt,
                groups,
                provider,
                model,
                metadata,
                pass_timeout,
                req_id=req_id,
                debug_llm_io=debug_llm_io,
            )
            elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
            results[pass_name] = (
                pass_rows,
                debug_records,
                pass_csv_segments,
                elapsed_ms,
                pass_errors,
            )
            if pass_errors:
                break
    else:
        semaphore = asyncio.Semaphore(concurrency_limit)

        async def _bounded_execute(index: int, pass_name: str, system_prompt: str):
            position = pass_offsets.get(pass_name, index)
            if PASS_STAGGER_SECONDS > 0 and position > 0:
                delay = PASS_STAGGER_SECONDS * position
                log.debug(
                    "[passes] delaying pass=%s by %.1fs before submission", pass_name, delay
                )
                await asyncio.sleep(delay)
            async with semaphore:
                return await _execute(pass_name, system_prompt)

        tasks = [
            asyncio.create_task(_bounded_execute(idx, pass_name, system_prompt))
            for idx, (pass_name, system_prompt) in enumerate(runnable_passes)
        ]

        for task in asyncio.as_completed(tasks):
            name, pass_rows, debug_records, pass_csv_segments, elapsed_ms, pass_errors = await task
            results[name] = (
                pass_rows,
                debug_records,
                pass_csv_segments,
                elapsed_ms,
                pass_errors,
            )

    for pass_name, _system_prompt in pass_items:
        if pass_name in results:
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
            if not pass_errors and pass_rows:
                save_pass_cache(
                    file_hash,
                    getattr(state, "filename", None),
                    pass_name,
                    payload_preview,
                )
        elif pass_name in pass_outputs:
            continue

    try:
        merged = merge_pass_outputs(pass_outputs, req_id=req_id)
    except Exception:  # pragma: no cover - defensive
        log.exception("[passes %s] unhandled exception while constructing rows", req_id)
        return {
            "ok": False,
            "httpStatus": 500,
            "error": "merge_failed",
        }

    rows = merged.get("rows", [])
    merge_problems = merged.get("problems", [])

    metrics["total"] = round((time.perf_counter() - total_start) * 1000, 1)

    csv_text = encode_rows_to_csv(rows)
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

    response["cache"] = {
        "hits": cache_hits,
        "misses": cache_misses,
        "file_hash": file_hash,
        "stored_passes": sorted(pass_outputs.keys()),
    }

    debug_enabled = bool(payload.get("debug") or env("DEBUG", "").lower() in {"1", "true", "yes"})
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
