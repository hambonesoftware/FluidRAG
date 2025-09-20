# -*- coding: utf-8 -*-
from __future__ import annotations
from flask import Blueprint, request, jsonify, make_response
import os

from ..pipeline import preprocess as pp
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

        # Try legacy loader first, else new extractor
        load_pages = getattr(pp, "load_document_to_text_pages", None)
        if callable(load_pages):
            pages_linear = load_pages(pdf_path, sidecar_dir=sidecar_dir)
        else:
            layout = pp.extract_pages_with_layout(pdf_path, sidecar_dir=sidecar_dir)
            pages_linear = layout.get("pages_linear") or []

        # Prefer legacy chunker if present, else section-bounded
        chunks = []
        std_chunks = getattr(pp, "standard_pre_chunks", None)
        if callable(std_chunks):
            for ch in std_chunks(pdf_path, sidecar_dir=sidecar_dir, session_id=session_id):
                chunks.append(ch)
        else:
            for ch in pp.section_bounded_chunks_from_pdf(
                pdf_path,
                sidecar_dir=sidecar_dir,
                session_id=session_id,
            ):
                chunks.append(ch)

        def _chunk_sort_key(item):
            page_start = item.get("page_start")
            try:
                page_start = int(page_start)
            except Exception:
                page_start = 1
            section_id = str(item.get("section_id") or "")
            chunk_idx = item.get("chunk_index_in_section")
            try:
                chunk_idx = int(chunk_idx)
            except Exception:
                chunk_idx = 0
            return (page_start, section_id, chunk_idx)

        if chunks:
            chunks.sort(key=_chunk_sort_key)

        # Aggregate preview rows by section to surface fuller spans
        preview_sections = {}
        for ch in chunks:
            sec_id = str(ch.get("section_id") or "")
            sec_name = ch.get("section_title") or "Document"
            page_start = ch.get("page_start")
            page_end = ch.get("page_end")
            try:
                page_start_i = int(page_start)
            except Exception:
                page_start_i = 1
            try:
                page_end_i = int(page_end)
            except Exception:
                page_end_i = page_start_i
            key = (sec_id, sec_name)
            entry = preview_sections.setdefault(
                key,
                {
                    "section_number": sec_id,
                    "section_name": sec_name,
                    "chars": 0,
                    "page_start": page_start_i,
                    "page_end": page_end_i,
                },
            )
            entry["chars"] += len(ch.get("text") or "")
            if page_start_i < entry["page_start"]:
                entry["page_start"] = page_start_i
            if page_end_i > entry.get("page_end", page_end_i):
                entry["page_end"] = page_end_i

        preview_list = sorted(
            preview_sections.values(),
            key=lambda item: (item.get("page_start", 1), item.get("section_number", "")),
        )[:5]

        if session_id:
            state = get_state(session_id)
            if state is not None:
                state.pre_chunks = chunks

        resp = {
            "ok": True,
            "httpStatus": 200,
            "pages": len(pages_linear),
            "chunks": len(chunks),
            "pre_chunks": len(chunks),
            "preview": preview_list,
        }
        response = jsonify(resp)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response, 200

    except Exception as e:
        return jsonify({"ok": False, "httpStatus": 500, "error": str(e)}), 500
