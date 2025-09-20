# -*- coding: utf-8 -*-
from __future__ import annotations
from flask import Blueprint, request, jsonify, make_response
import os

from ..pipeline import preprocess as pp

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
            for ch in std_chunks(pdf_path, sidecar_dir=sidecar_dir):
                chunks.append(ch)
        else:
            for ch in pp.section_bounded_chunks_from_pdf(pdf_path, sidecar_dir=sidecar_dir):
                chunks.append(ch)

        resp = {
            "ok": True,
            "httpStatus": 200,
            "pages": len(pages_linear),
            "chunks": len(chunks),
            "preview": [
                {
                    "chars": len(ch.get("text", "")),
                    "section_name": ch.get("section_title", "Document"),
                    "section_number": ch.get("section_id", "1"),
                } for ch in chunks[:5]
            ],
        }
        response = jsonify(resp)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response, 200

    except Exception as e:
        return jsonify({"ok": False, "httpStatus": 500, "error": str(e)}), 500
