# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any, Dict, List

import httpx
from flask import Blueprint, request, jsonify, make_response

from ..pipeline.preprocess import extract_pages_with_layout, _sections_from_detected_headers
from ..llm.errors import LLMAuthError
from ..llm.factory import create_llm_client, provider_default_model
from ..parse.header_page_mode import select_candidates, build_adjudication_prompt
from ..parse.header_config import CONFIG
from ..state import get_state
from ..utils.envsafe import env
from ..utils.strings import s

bp = Blueprint("headers", __name__)

_SECTION_NUMBER_RE = re.compile(r"\d+")

log = logging.getLogger("FluidRAG.routes.headers")


def _section_sort_key(section: dict) -> tuple:
    page = int(section.get("page_start") or section.get("source_page") or 0)
    number = str(section.get("section_number") or section.get("id") or "")
    number_parts = tuple(int(part) for part in _SECTION_NUMBER_RE.findall(number))
    has_number = 0 if number_parts else 1
    sequence_index = int(section.get("sequence_index") or 0)
    line_idx = int(section.get("source_line_idx") or 0)
    return (page, has_number, number_parts, sequence_index, line_idx)

def _json_ok(data, code=200):
    resp = jsonify(data)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp, code

@bp.route("/api/determine-headers", methods=["POST", "OPTIONS"])
def determine_headers():
    # CORS preflight
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return resp

    try:
        data = request.get_json(force=True) or {}

        session_id = data.get("session_id") or data.get("session") or ""
        pdf_path   = data.get("pdf_path") or data.get("path")
        if not pdf_path and session_id:
            uploads_dir = os.getenv("UPLOAD_FOLDER", "uploads")
            pdf_path = os.path.join(uploads_dir, f"{session_id}.pdf")
        sidecar_dir = os.path.join("sidecars", session_id) if session_id else None

        layout = extract_pages_with_layout(pdf_path, sidecar_dir=sidecar_dir)
        pages_linear     = layout.get("pages_linear") or []
        pages_lines      = layout.get("pages_lines") or [p.splitlines() for p in pages_linear]
        page_line_styles = layout.get("page_line_styles") or [[{} for _ in (p or [])] for p in pages_lines]

        provider = s(data.get("provider")) or env("LLM_PROVIDER", "openrouter") or "openrouter"
        model = (
            s(data.get("model"))
            or provider_default_model(provider)
            or env("HEADER_MODEL", "x-ai/grok-4-fast:free")
            or "x-ai/grok-4-fast:free"
        )
        client = create_llm_client(provider) if CONFIG.get("llm_enabled", True) else None

        # 1) Heuristic candidates by page
        all_page_cands, debug_candidates = [], []
        for pi, lines in enumerate(pages_lines):
            styles = page_line_styles[pi] if page_line_styles and pi < len(page_line_styles) else [{} for _ in lines]
            cands  = select_candidates(lines, styles)
            all_page_cands.append(cands)
            if pi < 15:  # trim debug size
                debug_candidates.append({"page": pi+1, "candidates": cands[:12]})

        # 2) Batch LLM adjudication to avoid 429s
        adjudicated: Dict[int, List[int]] = {}
        llm_debug: List[Dict[str, Any]] = []
        if client and any(c for c in all_page_cands):
            pages = list(range(len(pages_lines)))
            batch_size = max(1, int(CONFIG.get("llm_batch_pages", 4)))
            max_batches = max(1, int(CONFIG.get("llm_max_batches", 5)))
            batches = [pages[i:i+batch_size] for i in range(0, len(pages), batch_size)][:max_batches]
            req_id = uuid.uuid4().hex[:8]
            temperature = float(CONFIG.get("llm_temperature", 0.0) or 0.0)
            timeout_s = float(CONFIG.get("headers_llm_timeout_seconds", 120.0) or 120.0)
            initial_backoff = max(0.1, float(CONFIG.get("llm_backoff_initial_ms", 600)) / 1000.0)
            backoff_factor = float(CONFIG.get("llm_backoff_factor", 1.7) or 1.7)
            backoff_ceiling = max(initial_backoff, float(CONFIG.get("llm_backoff_max_ms", 4500)) / 1000.0)
            max_attempts = max(1, int(CONFIG.get("llm_max_retries", 4)))

            system_prompt = (
                "You adjudicate section headings. Reply ONLY JSON per page id:\n"
                "[{\"page\":N,\"items\":[{\"section_number\":\"\",\"section_name\":\"\",\"line_idx\":0}]}]"
            )

            async def run_batch(batch_pages: List[int], batch_index: int) -> Dict[str, Any]:
                user_payload = []
                for p in batch_pages:
                    if not all_page_cands[p]:
                        continue
                    prompt = build_adjudication_prompt(
                        pages_linear[p] if p < len(pages_linear) else "\n".join(pages_lines[p]),
                        all_page_cands[p],
                        CONFIG.get("context_chars_per_candidate", 700),
                    )
                    user_payload.append({"page": p + 1, "prompt": prompt})

                if not user_payload:
                    return {"ok": True, "batch": batch_pages, "result": [], "skipped": True}

                payload_text = json.dumps(user_payload, ensure_ascii=False)
                backoff = initial_backoff

                for attempt in range(1, max_attempts + 1):
                    try:
                        log.info(
                            "[headers] req=%s batch=%d/%d attempting adjudication pages=%s",
                            req_id,
                            batch_index + 1,
                            len(batches),
                            ",".join(str(p + 1) for p in batch_pages),
                        )
                        response_text = await asyncio.wait_for(
                            client.acomplete(
                                model=model,
                                system=system_prompt,
                                user=payload_text,
                                temperature=temperature,
                                max_tokens=120_000,
                                extra={"stream": False},
                            ),
                            timeout=timeout_s,
                        )
                        parsed = []
                        if isinstance(response_text, str) and response_text.strip():
                            try:
                                parsed = json.loads(response_text)
                            except json.JSONDecodeError:
                                preview = response_text.strip()[:400]
                                log.warning(
                                    "[headers] req=%s batch=%d JSON parse failed; preview=%r",
                                    req_id,
                                    batch_index + 1,
                                    preview,
                                )
                        return {
                            "ok": True,
                            "batch": batch_pages,
                            "result": parsed,
                            "raw": response_text,
                            "attempts": attempt,
                        }
                    except asyncio.TimeoutError:
                        log.error(
                            "[headers] req=%s batch=%d timeout after %.1fs",
                            req_id,
                            batch_index + 1,
                            timeout_s,
                        )
                        return {
                            "ok": False,
                            "batch": batch_pages,
                            "error": f"timeout after {timeout_s:.1f}s",
                            "result": [],
                        }
                    except LLMAuthError as exc:
                        log.error("[headers] req=%s auth error: %s", req_id, exc)
                        return {"ok": False, "batch": batch_pages, "error": str(exc), "result": []}
                    except httpx.HTTPStatusError as exc:
                        status = exc.response.status_code if exc.response else None
                        message = f"HTTP {status}: {exc}"
                        if status == 429 and attempt < max_attempts:
                            await asyncio.sleep(backoff)
                            backoff = min(backoff * backoff_factor, backoff_ceiling)
                            continue
                        log.error("[headers] req=%s batch=%d transport error: %s", req_id, batch_index + 1, message)
                        return {"ok": False, "batch": batch_pages, "error": message, "result": []}
                    except Exception as exc:
                        message = str(exc)
                        if attempt < max_attempts and ("429" in message or "Too Many Requests" in message):
                            await asyncio.sleep(backoff)
                            backoff = min(backoff * backoff_factor, backoff_ceiling)
                            continue
                        log.exception("[headers] req=%s batch=%d exception", req_id, batch_index + 1)
                        return {"ok": False, "batch": batch_pages, "error": message, "result": []}

                return {"ok": False, "batch": batch_pages, "error": "LLM retry exhausted", "result": []}

            async def run_all_batches() -> List[Dict[str, Any]]:
                outputs: List[Dict[str, Any]] = []
                for idx, batch in enumerate(batches):
                    outputs.append(await run_batch(batch, idx))
                return outputs

            outs = asyncio.run(run_all_batches())

            for out in outs:
                if len(llm_debug) < 6:
                    llm_debug.append(out)
                else:
                    llm_debug.append({"ok": out.get("ok", False), "batch": out.get("batch")})
                if not out.get("ok"):
                    continue
                for item in out.get("result") or []:
                    try:
                        pg = int(item.get("page", 0))
                    except Exception:
                        continue
                    arr = item.get("items") or []
                    chosen: List[int] = []
                    for it in arr:
                        try:
                            chosen.append(int(it.get("line_idx")))
                        except Exception:
                            continue
                    if pg >= 1:
                        adjudicated[pg - 1] = chosen

            transport_debug = client.drain_debug_records()
        else:
            transport_debug = []

        # 3) Merge: if LLM adjudicated a page, use that; else fallback to top-K heuristics
        results = []
        sections_count = 0
        topk = int(CONFIG.get("fallback_top_k_per_page", 3))
        for pi, cands in enumerate(all_page_cands):
            chosen_idx = adjudicated.get(pi)
            headers = []
            if chosen_idx is not None:
                # keep original order on page
                for ci in cands:
                    if ci["line_idx"] in chosen_idx:
                        headers.append({
                            "line_idx": ci["line_idx"],
                            "text": ci["text"],
                            "section_number": ci.get("section_number", ""),
                            "level": ci.get("level", 3),
                            "score": max(ci.get("score", 0.0), 3.0),
                            "style": ci.get("style", {}),
                        })
            else:
                # fallback: top-K best heuristic
                for ci in cands[:topk]:
                    headers.append({
                        "line_idx": ci["line_idx"],
                        "text": ci["text"],
                        "section_number": ci.get("section_number", ""),
                        "level": ci.get("level", 3),
                        "score": ci.get("score", 0.0),
                        "style": ci.get("style", {}),
                    })

            sections_count += len(headers)
            results.append({"page": pi+1, "headers": headers})

        if session_id:
            session_state = get_state(session_id)
            if session_state is not None:
                session_state.headers = results

        preview = []
        detected_sections = _sections_from_detected_headers(pages_lines, results)
        for section in sorted(detected_sections, key=_section_sort_key):
            # Skip the preamble helper bucket – callers are interested in explicit headers only.
            if section.get("id") == "0" and (section.get("title") or "").lower() == "preamble":
                continue

            content_lines = section.get("content") or []
            if not content_lines:
                continue

            text_lines = [line.rstrip("\n") for line in content_lines if isinstance(line, str)]
            if not text_lines:
                continue

            header_text = section.get("title") or text_lines[0].strip()
            body_lines = text_lines[1:]
            body_text = "\n".join(body_lines).strip("\n")
            full_text = "\n".join(text_lines).strip("\n")

            preview.append(
                {
                    "chars": len(full_text),
                    "section_name": header_text,
                    "section_number": section.get("section_number") or section.get("id") or "",
                    "page_found": section.get("page_start"),
                    "page_start": section.get("page_start"),
                    "heading_level": section.get("heading_level"),
                    "content": body_text,
                }
            )

        return _json_ok({
            "ok": True,
            "httpStatus": 200,
            "sections": sections_count,
            "preview": preview,
            "debug": {
                "candidates": debug_candidates,  # first pages only to keep payload light
                "adjudicated_pages": sorted(list(adjudicated.keys())),
                "llm_batches": len(llm_debug),
                "llm_debug": llm_debug,
                "llm_transport": transport_debug,
                "provider": provider,
                "model": model,
            }
        })
    except Exception as e:
        return _json_ok({"ok": False, "httpStatus": 500, "error": str(e)}, 500)
