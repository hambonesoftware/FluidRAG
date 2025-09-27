# -*- coding: utf-8 -*-
from __future__ import annotations

import copy
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, request, jsonify, make_response

from ..pipeline.preprocess import extract_pages_with_layout, _sections_from_detected_headers
from ..persistence import clear_headers_cache, get_headers_cache, save_headers_cache
from ..parse.header_page_mode import (
    dump_appendix_audit,
    select_candidates,
    write_header_debug_manifest,
    write_page_debug,
)
from ..parse.header_config import CONFIG
from ..state import get_state
from ..utils.strings import s

bp = Blueprint("headers", __name__)

_SECTION_NUMBER_RE = re.compile(r"\d+")

log = logging.getLogger("FluidRAG.routes.headers")


def _is_truthy_flag(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no", "off", "none", "null"}:
            return False
        return True
    return bool(value)


def _sanitize_component(value: Any, default: str = "document") -> str:
    text = str(value or "").strip()
    if not text:
        return default
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", text)
    safe = safe.strip("_")
    return safe or default


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
        pdf_path = data.get("pdf_path") or data.get("path")
        if not pdf_path and session_id:
            uploads_dir = os.getenv("UPLOAD_FOLDER", "uploads")
            pdf_path = os.path.join(uploads_dir, f"{session_id}.pdf")
        sidecar_dir = os.path.join("sidecars", session_id) if session_id else None

        session_state = get_state(session_id) if session_id else None
        file_hash = getattr(session_state, "file_hash", None) if session_state else None

        force_refresh = _is_truthy_flag(data.get("force_refresh"))

        debug_requested = _is_truthy_flag(data.get("debug"))
        debug_dir_override = s(data.get("debug_dir") or data.get("headers_debug_dir"))
        prev_debug = CONFIG.get("debug", False)
        prev_dir = CONFIG.get("debug_dir")

        doc_tag_source = (
            data.get("doc_tag")
            or session_id
            or os.path.splitext(os.path.basename(pdf_path or ""))[0]
        )
        doc_tag = _sanitize_component(doc_tag_source, "document")
        header_debug_dir: Optional[str] = None
        page_debug_snapshots: List[Tuple[int, List[dict], str]] = []

        try:
            CONFIG["debug"] = bool(debug_requested)
            if debug_requested and debug_dir_override:
                CONFIG["debug_dir"] = debug_dir_override

            debug_active = bool(CONFIG.get("debug"))
            base_debug_dir = CONFIG.get("debug_dir") or "./_debug/headers"
            if debug_active:
                header_debug_dir = os.path.join(base_debug_dir, doc_tag)

            cached = get_headers_cache(file_hash)
            if cached and not force_refresh:
                results = list(cached.get("results") or [])
                if session_state is not None:
                    session_state.headers = results
                response_payload = dict(cached.get("response") or {})
                debug_payload = response_payload.setdefault("debug", {})
                if isinstance(debug_payload, dict):
                    selected_counts = []
                    for page in results:
                        if not isinstance(page, dict):
                            continue
                        headers = page.get("headers")
                        if not isinstance(headers, list):
                            headers = []
                        selected_counts.append(len(headers))
                    heuristics = debug_payload.get("heuristics")
                    if not isinstance(heuristics, dict):
                        heuristics = {
                            "heuristic_only": True,
                            "fallback_topk": int(CONFIG.get("fallback_top_k_per_page", 3)),
                            "selected_headers": sum(selected_counts),
                            "selected_per_page": selected_counts,
                        }
                    else:
                        heuristics = dict(heuristics)
                        heuristics.setdefault("heuristic_only", True)
                        heuristics.setdefault(
                            "fallback_topk", int(CONFIG.get("fallback_top_k_per_page", 3))
                        )
                        heuristics.setdefault("selected_headers", sum(selected_counts))
                        heuristics.setdefault("selected_per_page", selected_counts)
                    debug_payload["heuristics"] = heuristics
                    for legacy_key in (
                        "llm_batches",
                        "llm_debug",
                        "llm_transport",
                        "provider",
                        "model",
                        "adjudicated_pages",
                    ):
                        debug_payload.pop(legacy_key, None)
                response_payload.update(
                    {
                        "ok": True,
                        "httpStatus": 200,
                        "cache": {"hit": True, "section": "headers", "bypassed": False},
                        "from_cache": True,
                    }
                )
                if debug_active and header_debug_dir:
                    response_payload.setdefault("debug", {})
                    response_payload["debug"].setdefault("files", {})
                    response_payload["debug"]["files"]["directory"] = header_debug_dir
                    response_payload["debug"]["files"]["doc"] = doc_tag
                return _json_ok(response_payload)

            if cached and force_refresh:
                log.info(
                    "[headers] cache bypass requested for session=%s hash=%s",
                    session_id,
                    file_hash,
                )

                clear_headers_cache(file_hash)
                if session_state is not None:
                    session_state.headers = []

            layout = extract_pages_with_layout(pdf_path, sidecar_dir=sidecar_dir)
            pages_linear = layout.get("pages_linear") or []
            pages_lines = layout.get("pages_lines") or [p.splitlines() for p in pages_linear]
            page_line_styles = layout.get("page_line_styles") or [
                [{} for _ in (p or [])] for p in pages_lines
            ]

            all_page_cands, debug_candidates = [], []
            for pi, lines in enumerate(pages_lines):
                styles = (
                    page_line_styles[pi]
                    if page_line_styles and pi < len(page_line_styles)
                    else [{} for _ in lines]
                )
                cands = select_candidates(lines, styles)
                all_page_cands.append(cands)
                if pi < 15:
                    debug_candidates.append({"page": pi + 1, "candidates": cands[:12]})

                page_text = (
                    pages_linear[pi]
                    if pi < len(pages_linear)
                    else "\n".join(lines)
                )
                snapshot = [copy.deepcopy(c) for c in cands]
                page_debug_snapshots.append((pi, snapshot, page_text))
                if debug_active:
                    write_page_debug(doc_tag, pi, page_text, snapshot)
            results = []
            sections_count = 0
            topk = int(CONFIG.get("fallback_top_k_per_page", 3))
            candidate_counts: List[int] = []
            selected_counts: List[int] = []
            for pi, cands in enumerate(all_page_cands):
                headers = []
                candidate_counts.append(len(cands))
                for ci in cands[:topk]:
                    headers.append(
                        {
                            "line_idx": ci["line_idx"],
                            "text": ci["text"],
                            "section_number": ci.get("section_number", ""),
                            "level": ci.get("level", 3),
                            "score": ci.get("score", 0.0),
                            "style": ci.get("style", {}),
                        }
                    )

                sections_count += len(headers)
                selected_counts.append(len(headers))
                results.append({"page": pi + 1, "headers": headers})

            if session_state is not None:
                session_state.headers = results

            preview = []
            detected_sections = _sections_from_detected_headers(pages_lines, results)
            for section in sorted(detected_sections, key=_section_sort_key):
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

            if debug_active:
                dump_appendix_audit(doc_tag, page_debug_snapshots)
                write_header_debug_manifest(doc_tag, page_debug_snapshots, results)
            # Candidate audit payloads are emitted by the EFHG pipeline; the
            # header-only route stops after writing optional debug manifests.

            heuristic_debug = {
                "pages": len(all_page_cands),
                "pages_with_candidates": sum(1 for count in candidate_counts if count),
                "total_candidates": sum(candidate_counts),
                "selected_headers": sections_count,
                "fallback_topk": topk,
                "candidates_per_page": candidate_counts,
                "selected_per_page": selected_counts,
                "heuristic_only": True,
            }

            response_payload = {
                "ok": True,
                "httpStatus": 200,
                "sections": sections_count,
                "preview": preview,
                "cache": {
                    "hit": False,
                    "section": "headers",
                    "bypassed": bool(cached and force_refresh),
                },
                "debug": {
                    "candidates": debug_candidates,
                    "heuristics": heuristic_debug,
                },
            }

            store_response = dict(response_payload)
            store_response.pop("cache", None)
            store_response.pop("from_cache", None)
            save_headers_cache(
                file_hash,
                getattr(session_state, "filename", None),
                results,
                store_response,
            )

            if debug_active and header_debug_dir:
                response_payload.setdefault("debug", {})
                response_payload["debug"].setdefault("files", {})
                response_payload["debug"]["files"]["directory"] = header_debug_dir
                response_payload["debug"]["files"]["doc"] = doc_tag

            return _json_ok(response_payload)
        finally:
            CONFIG["debug"] = prev_debug
            CONFIG["debug_dir"] = prev_dir
    except Exception as e:
        return _json_ok({"ok": False, "httpStatus": 500, "error": str(e)}, 500)

