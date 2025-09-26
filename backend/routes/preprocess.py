# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path
import json
from datetime import datetime, timezone
import logging

from flask import Blueprint, request, jsonify, make_response
import os

from fluidrag.config import load_config

from ..chunking.token_chunker import (
    MICRO_MAX_TOKENS,
    MICRO_OVERLAP_TOKENS,
    micro_chunks_by_tokens,
)
from ..pipeline import preprocess as pp
from ..pipeline.uf_pipeline import prepare_pass_chunk, run_pipeline as run_uf_pipeline
from ..persistence import get_preprocess_cache, save_preprocess_cache
from ..state import get_state


log = logging.getLogger("FluidRAG.api.preprocess")


def _chunk_debug_dir() -> Path:
    override = os.environ.get("FLUIDRAG_DEBUG_DIR")
    base = Path(override) if override else Path("debug") / "chunks"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _sanitize_filename_tag(tag: str | None) -> str:
    if not tag:
        return "document"
    safe = "".join(
        ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in str(tag)
    )
    return safe or "document"


def export_preprocess_debug(
    *,
    session_id: str | None,
    doc_id: str,
    doc_name: str,
    macro_chunks: list,
    micro_chunks: list,
    response_payload: dict,
    preprocess_debug_payload: dict | None,
    chunk_config: dict | None,
    page_records: list | None,
    cache_hit: bool,
) -> Path:
    """Write the preprocess output (chunks + metadata) to ``/debug/chunks``."""

    debug_dir = _chunk_debug_dir()
    tag = _sanitize_filename_tag(doc_id or session_id or doc_name)
    outfile = debug_dir / f"{tag}.preprocess.json"

    def _json_safe(value: object) -> object:
        try:
            return json.loads(json.dumps(value, ensure_ascii=False))
        except Exception:
            return value

    payload: dict[str, object] = {
        "session_id": session_id or None,
        "doc_id": doc_id,
        "doc_name": doc_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cache_hit": bool(cache_hit),
        "response": _json_safe(response_payload),
        "macro_chunks": _json_safe(macro_chunks or []),
        "micro_chunks": _json_safe(micro_chunks or []),
        "preprocess_debug": _json_safe(preprocess_debug_payload or {}),
        "config": _json_safe(chunk_config or {}),
    }
    if page_records is not None:
        payload["pages"] = _json_safe(page_records)

    with outfile.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    return outfile

bp = Blueprint("preprocess", __name__)

# Accept POST + OPTIONS (CORS preflight)
@bp.route("/api/preprocess", methods=["POST", "OPTIONS"])
def preprocess_route():
    # Handle preflight explicitly
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        # Allow the headers/methods your frontend sends
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return resp

    try:
        data = request.get_json(force=True) or {}
        session_id = data.get("session_id") or data.get("session") or ""
        pdf_path = data.get("pdf_path") or data.get("path")
        if not pdf_path and session_id:
            pdf_path = os.path.join("uploads", f"{session_id}.pdf")
        sidecar_dir = os.path.join("sidecars", session_id) if session_id else None

        state = get_state(session_id) if session_id else None
        file_hash = getattr(state, "file_hash", None) if state else None
        force_refresh = bool(data.get("force_refresh"))

        raw_doc_name = (
            (state.filename if state and getattr(state, "filename", None) else None)
            or os.path.splitext(os.path.basename(pdf_path or ""))[0]
            or session_id
            or "document"
        )
        doc_name = str(raw_doc_name)
        doc_id = Path(doc_name).stem or "document"

        cached = get_preprocess_cache(file_hash) if not force_refresh else None
        if cached:
            cached_macro = [dict(chunk) for chunk in cached.get("macro_chunks") or cached.get("chunks", [])]
            cached_micro = [dict(chunk) for chunk in cached.get("micro_chunks", [])]
            cached_debug = cached.get("debug") if isinstance(cached, dict) else None
            if state is not None:
                state.pre_chunks = cached_macro
                state.macro_chunks = cached_macro
                state.micro_chunks = cached_micro
                state.uf_chunks = cached_micro
                if isinstance(cached_debug, dict):
                    state.debug = dict(cached_debug)
            response_payload = dict(cached.get("response") or {})
            response_payload.update(
                {
                    "ok": True,
                    "httpStatus": 200,
                    "macro_chunks": len(cached_macro),
                    "micro_chunks": len(cached_micro),
                    "pre_chunks": len(cached_macro),
                    "cache": {"hit": True, "section": "preprocess"},
                    "from_cache": True,
                }
            )
            response_payload.setdefault("pages", response_payload.get("pages") or 0)
            response_payload.setdefault(
                "chunks", response_payload.get("chunks") or len(cached_macro)
            )
            if state is not None:
                uf_summary = response_payload.get("uf_pipeline")
                state.uf_pipeline = uf_summary if isinstance(uf_summary, dict) else None
                tables_payload = response_payload.get("tables")
                if isinstance(tables_payload, list):
                    state.uf_tables = tables_payload
                headers_payload = response_payload.get("headers")
                if isinstance(headers_payload, list):
                    state.headers = headers_payload
            try:
                export_preprocess_debug(
                    session_id=session_id or None,
                    doc_id=doc_id,
                    doc_name=doc_name,
                    macro_chunks=cached_macro,
                    micro_chunks=cached_micro,
                    response_payload=response_payload,
                    preprocess_debug_payload=cached_debug if isinstance(cached_debug, dict) else None,
                    chunk_config=None,
                    page_records=None,
                    cache_hit=True,
                )
            except Exception:
                pass

            response = jsonify(response_payload)
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response, 200

        layout = pp.extract_pages_with_layout(pdf_path, sidecar_dir=sidecar_dir)
        pages_linear = layout.get("pages_linear") or []

        cfg = load_config(Path("config") / "fluidrag.yaml")
        chunk_cfg = (cfg.get("chunking", {}) or {})
        micro_cfg = chunk_cfg.get("micro", {})
        macro_cfg = chunk_cfg.get("macro", {})

        page_records = [
            {"page": idx + 1, "text": text}
            for idx, text in enumerate(pages_linear)
        ]

        joined_text_parts = [
            str(page.get("text") or "").strip()
            for page in page_records
            if page.get("text")
        ]
        preprocess_debug: dict = {"preprocess": {}}
        if joined_text_parts:
            doc_text = "\n\n".join(joined_text_parts)
            token_chunks = micro_chunks_by_tokens(doc_text)
            chunking_payload = {
                "config": {
                    "micro_max_tokens": MICRO_MAX_TOKENS,
                    "micro_overlap_tokens": MICRO_OVERLAP_TOKENS,
                    "tokenizer": "tiktoken/cl100k_base (fallback est. if unavailable)",
                },
                "summary": {
                    "micro_chunk_count": len(token_chunks),
                    "total_micro_tokens": sum(
                        chunk.get("token_count", 0) for chunk in token_chunks
                    ),
                },
                "micro_chunks": [
                    {
                        "idx": idx,
                        "token_count": chunk.get("token_count", 0),
                        "note": chunk.get("note", ""),
                        "token_span": chunk.get("token_span"),
                        "text_preview": chunk.get("text_preview", ""),
                        "text_hash": chunk.get("text_hash"),
                    }
                    for idx, chunk in enumerate(token_chunks)
                ],
            }
            preprocess_debug["preprocess"]["chunking"] = chunking_payload
        preprocess_debug_payload = (
            dict(preprocess_debug) if preprocess_debug.get("preprocess") else None
        )

        try:
            uf_result = run_uf_pipeline(
                pdf_path,
                doc_id=doc_id,
                session_id=session_id or None,
                sidecar_dir=sidecar_dir,
                llm_client=None,
                pre_extracted=layout,
            )
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("[preprocess] UF pipeline failed for %s: %s", doc_id, exc)
            raise

        uf_summary = uf_result.summary()
        uf_debug = {
            "summary": uf_summary,
            "artifacts": {key: str(path) for key, path in uf_result.artifacts.items()},
            "efhg_preview": uf_result.efhg_spans[:10],
            "header_repairs": uf_result.headers.repairs,
        }
        if preprocess_debug_payload is None:
            preprocess_debug_payload = {"uf_pipeline": uf_debug}
        else:
            preprocess_debug_payload = dict(preprocess_debug_payload)
            preprocess_debug_payload["uf_pipeline"] = uf_debug

        macro_chunks = [
            prepare_pass_chunk(chunk, document=doc_name, position=idx)
            for idx, chunk in enumerate(uf_result.uf_chunks)
        ]

        micro_chunks = [dict(chunk) for chunk in macro_chunks]

        preview_list = []
        for macro in macro_chunks[:5]:
            preview_list.append(
                {
                    "section_number": macro.get("section_number") or "",
                    "section_name": macro.get("section_title") or "Document",
                    "chars": len(macro.get("text") or ""),
                    "page_start": macro.get("page_start"),
                    "page_end": macro.get("page_end"),
                    "micro_chunks": 1,
                }
            )

        if state is not None:
            state.pre_chunks = macro_chunks
            state.macro_chunks = macro_chunks
            state.micro_chunks = micro_chunks
            state.uf_chunks = micro_chunks
            state.uf_pipeline = uf_summary
            state.uf_tables = uf_result.tables
            state.headers = uf_result.headers.pages
            state.debug = (
                preprocess_debug_payload.copy()
                if isinstance(preprocess_debug_payload, dict)
                else None
            )

        resp = {
            "ok": True,
            "httpStatus": 200,
            "pages": len(pages_linear),
            "chunks": len(macro_chunks),
            "pre_chunks": len(macro_chunks),
            "macro_chunks": len(macro_chunks),
            "micro_chunks": len(micro_chunks),
            "preview": preview_list,
            "uf_pipeline": uf_summary,
            "headers": uf_result.headers.pages,
            "tables": uf_result.tables,
            "cache": {"hit": False, "section": "preprocess"},
        }
        response = jsonify(resp)
        response.headers["Access-Control-Allow-Origin"] = "*"

        store_resp = dict(resp)
        store_resp.pop("cache", None)
        store_resp.pop("from_cache", None)
        save_preprocess_cache(
            file_hash,
            getattr(state, "filename", None),
            store_resp,
            macro_chunks,
            micro_chunks,
            preprocess_debug_payload,
        )

        chunk_config_export = {
            "micro": dict(micro_cfg) if isinstance(micro_cfg, dict) else micro_cfg,
            "macro": dict(macro_cfg) if isinstance(macro_cfg, dict) else macro_cfg,
            "token_chunker": {
                "micro_max_tokens": MICRO_MAX_TOKENS,
                "micro_overlap_tokens": MICRO_OVERLAP_TOKENS,
            },
        }

        try:
            export_preprocess_debug(
                session_id=session_id or None,
                doc_id=doc_id,
                doc_name=doc_name,
                macro_chunks=macro_chunks,
                micro_chunks=micro_chunks,
                response_payload=resp,
                preprocess_debug_payload=preprocess_debug_payload,
                chunk_config=chunk_config_export,
                page_records=page_records,
                cache_hit=False,
            )
        except Exception:
            pass

        return response, 200

    except Exception as e:
        return jsonify({"ok": False, "httpStatus": 500, "error": str(e)}), 500
