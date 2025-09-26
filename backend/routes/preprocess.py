# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path

from flask import Blueprint, request, jsonify, make_response
import os

from fluidrag.config import load_config

from ..chunking.atomic_chunker import AtomicChunker
from ..chunking.macro_chunker import MacroChunker
from ..chunking.token_chunker import (
    MICRO_MAX_TOKENS,
    MICRO_OVERLAP_TOKENS,
    micro_chunks_by_tokens,
)
from ..pipeline import preprocess as pp
from ..persistence import get_preprocess_cache, save_preprocess_cache
from ..state import get_state

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

        cached = get_preprocess_cache(file_hash) if not force_refresh else None
        if cached:
            cached_macro = [dict(chunk) for chunk in cached.get("macro_chunks") or cached.get("chunks", [])]
            cached_micro = [dict(chunk) for chunk in cached.get("micro_chunks", [])]
            cached_debug = cached.get("debug") if isinstance(cached, dict) else None
            if state is not None:
                state.pre_chunks = cached_macro
                state.macro_chunks = cached_macro
                state.micro_chunks = cached_micro
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
            response = jsonify(response_payload)
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response, 200

        # Try legacy loader first, else new extractor
        load_pages = getattr(pp, "load_document_to_text_pages", None)
        if callable(load_pages):
            pages_linear = load_pages(pdf_path, sidecar_dir=sidecar_dir)
        else:
            layout = pp.extract_pages_with_layout(pdf_path, sidecar_dir=sidecar_dir)
            pages_linear = layout.get("pages_linear") or []

        cfg = load_config(Path("config") / "fluidrag.yaml")
        chunk_cfg = (cfg.get("chunking", {}) or {})
        micro_cfg = chunk_cfg.get("micro", {})
        macro_cfg = chunk_cfg.get("macro", {})

        doc_name = (state.filename if state and getattr(state, "filename", None) else None) or os.path.splitext(os.path.basename(pdf_path or ""))[0] or session_id or "document"
        doc_id = Path(doc_name).stem or "document"
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

        header_spans = []
        if state is not None and state.headers:
            for page_entry in state.headers:
                headers = page_entry.get("headers") if isinstance(page_entry, dict) else None
                if not isinstance(headers, list):
                    continue
                for header in headers:
                    if not isinstance(header, dict):
                        continue
                    clause = header.get("section_number") or header.get("clause")
                    text = header.get("text") or header.get("heading")
                    if clause and text:
                        header_spans.append({"clause": clause, "text": text})

        chunker = AtomicChunker(micro_cfg)
        micro_chunks = chunker.chunk(doc_id, page_records, header_spans)
        for micro in micro_chunks:
            micro.setdefault("micro_id", micro.get("id"))
            span = micro.get("page_span") or [1, 1]
            try:
                page_start = int(span[0])
            except Exception:
                page_start = 1
            try:
                page_end = int(span[1])
            except Exception:
                page_end = page_start
            micro.setdefault("page_start", page_start)
            micro.setdefault("page_end", page_end)
            micro.setdefault("pages", list(range(page_start, page_end + 1)))

        macro_chunker = MacroChunker(macro_cfg)
        raw_macros = macro_chunker.build(micro_chunks)

        macro_chunks = []
        for idx, macro in enumerate(raw_macros):
            enriched = dict(macro)
            page_span = enriched.get("page_span") or [1, 1]
            try:
                page_start = int(page_span[0])
            except Exception:
                page_start = 1
            try:
                page_end = int(page_span[1])
            except Exception:
                page_end = page_start
            pages = enriched.get("pages") or list(range(page_start, page_end + 1))
            hierarchy = enriched.get("hierarchy") or {}
            heading_values = hierarchy.get("headings") or []
            first_heading = heading_values[0] if heading_values else None
            section_title = (
                enriched.get("section_title")
                or first_heading
                or enriched.get("hier_path")
                or "Document"
            )
            section_number = enriched.get("section_id") or hierarchy.get("section")
            enriched.update(
                {
                    "chunk_id": enriched.get("macro_id"),
                    "chunk_index_in_section": idx,
                    "page_start": page_start,
                    "page_end": page_end,
                    "page": page_start,
                    "pages": pages,
                    "section_number": section_number,
                    "section_title": section_title,
                    "section_name": section_title,
                    "document": doc_name,
                    "chunk_type": "macro",
                }
            )
            meta = dict(enriched.get("meta") or {})
            meta.setdefault("hierarchy", hierarchy)
            meta.setdefault("micro_children", list(enriched.get("micro_children") or []))
            enriched["meta"] = meta
            macro_chunks.append(enriched)

        def _macro_sort_key(item):
            return (
                int(item.get("page_start", 1) or 1),
                str(item.get("section_number") or ""),
                int(item.get("chunk_index_in_section", 0) or 0),
            )

        macro_chunks.sort(key=_macro_sort_key)

        preview_list = []
        for macro in macro_chunks[:5]:
            preview_list.append(
                {
                    "section_number": macro.get("section_number") or "",
                    "section_name": macro.get("section_title") or "Document",
                    "chars": len(macro.get("text") or ""),
                    "page_start": macro.get("page_start"),
                    "page_end": macro.get("page_end"),
                    "micro_chunks": len(macro.get("micro_children") or []),
                }
            )

        if state is not None:
            state.pre_chunks = macro_chunks
            state.macro_chunks = macro_chunks
            state.micro_chunks = micro_chunks
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

        return response, 200

    except Exception as e:
        return jsonify({"ok": False, "httpStatus": 500, "error": str(e)}), 500
