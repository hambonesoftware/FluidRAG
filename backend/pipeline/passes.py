# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import base64
import csv
import io
import logging

import os
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..llm.errors import LLMAuthError, LLMError
from ..llm.factory import create_llm_client, provider_default_model
from ..prompts import PASS_PROMPTS
from ..state import get_state
from ..utils.envsafe import env, s

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
DEFAULT_PASS_CONCURRENCY = 1
DEFAULT_PASS_TIMEOUT_S = 120

CSV_COLUMNS = ["Document", "(Sub)Section #", "(Sub)Section Name", "Specification", "Pass"]


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
    doc = chunk.get("document") or "Document"
    sec_num = str(chunk.get("section_number") or chunk.get("section_id") or "").strip()
    sec_name = str(chunk.get("section_name") or chunk.get("section_title") or "").strip()
    page_start = chunk.get("page_start") or chunk.get("page") or 1
    page_end = chunk.get("page_end") or page_start
    body = (chunk.get("text") or "").strip()
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
        if (chunk.get("text") or "").strip()
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
            normalized = {col: row.get(col, "").strip() for col in CSV_COLUMNS}
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
        try:
            content = await asyncio.wait_for(
                client.acomplete(
                    model=model,
                    system=system_prompt,
                    user=prompt,
                    temperature=0.0,
                    max_tokens=4096,
                ),
                timeout=timeout_s,
            )
        except (LLMAuthError, LLMError) as exc:
            errors.append(
                {
                    "batch": batch_index,
                    "error": str(exc),
                    "pass": pass_name,
                    "model": model,
                    "provider": provider,
                }
            )
            log.error("[passes] pass=%s batch=%d auth/llm error: %s", pass_name, batch_index + 1, exc)
            break
        except asyncio.TimeoutError:
            msg = "LLM batch timed out"
            errors.append(
                {
                    "batch": batch_index,
                    "error": msg,
                    "pass": pass_name,
                    "timeout_s": timeout_s,
                    "model": model,
                    "provider": provider,
                }
            )
            log.error("[passes] pass=%s batch=%d timeout", pass_name, batch_index + 1)
            break
        except Exception as exc:
            errors.append(
                {
                    "batch": batch_index,
                    "error": str(exc),
                    "pass": pass_name,
                    "model": model,
                    "provider": provider,
                }
            )
            log.exception("[passes] pass=%s batch=%d exception", pass_name, batch_index + 1)

            break
        else:
            rows, csv_block, _json_block = _parse_pass_response(content, pass_name)
            if rows:
                pass_rows.extend(rows)
            if csv_block:
                csv_segments.append(csv_block)

    debug_records = client.drain_debug_records()
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

    rows: List[Dict[str, str]] = []
    csv_segments: List[str] = []
    llm_debug: List[Dict[str, Any]] = []
    metrics: Dict[str, float] = {}
    all_errors: List[Dict[str, Any]] = []

    pass_items = list(PASS_PROMPTS.items())
    concurrency_limit = _resolve_pass_concurrency(payload)
    pass_timeout = _resolve_pass_timeout(payload)

    log.info(
        "[passes] session=%s provider=%s model=%s passes=%d groups=%d concurrency=%d timeout=%.1fs",
        session_id,
        provider,
        model,
        len(pass_items),
        len(groups),
        concurrency_limit,
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

    if concurrency_limit <= 1 or len(pass_items) <= 1:
        for pass_name, system_prompt in pass_items:
            name, pass_rows, debug_records, pass_csv_segments, elapsed_ms, pass_errors = await _execute_pass(

                pass_name, system_prompt
            )
            metrics[name] = elapsed_ms
            rows.extend(pass_rows)
            csv_segments.extend(pass_csv_segments)
            llm_debug.extend(debug_records)
            all_errors.extend(pass_errors)

    else:
        semaphore = asyncio.Semaphore(concurrency_limit)
        async def _bounded_execute(pass_name: str, system_prompt: str):
            async with semaphore:
                return await _execute_pass(pass_name, system_prompt)

        tasks = [
            asyncio.create_task(_bounded_execute(pass_name, system_prompt))
            for pass_name, system_prompt in pass_items
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
            rows.extend(pass_rows)
            csv_segments.extend(pass_csv_segments)
            llm_debug.extend(debug_records)
            all_errors.extend(pass_errors)

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
