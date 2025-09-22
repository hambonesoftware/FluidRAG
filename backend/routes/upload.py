# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import tempfile
import logging
import hashlib
from flask import Blueprint, request, jsonify, make_response
from werkzeug.utils import secure_filename

from .. import config
from ..persistence import load_document_cache
from ..state import PipelineState, PIPELINE_STATES, new_session_id

log = logging.getLogger("FluidRAG.api.upload")

bp = Blueprint("upload", __name__)

# If your config.ALLOWED_EXT is a set like {".pdf"}, we keep using it.
# Otherwise, default to only PDF.
def _is_allowed(filename: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    try:
        allowed = getattr(config, "ALLOWED_EXT", {".pdf"})
        return ext in allowed
    except Exception:
        return ext == ".pdf"

@bp.route("/api/upload", methods=["POST", "OPTIONS"])
def upload_file():
    # --- CORS preflight ---
    if request.method == "OPTIONS":
        resp = make_response("", 204)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return resp

    try:
        if "file" not in request.files:
            return jsonify({"ok": False, "httpStatus": 400, "error": "No file provided"}), 400

        f = request.files["file"]
        filename = secure_filename(f.filename or "upload")
        if not filename:
            return jsonify({"ok": False, "httpStatus": 400, "error": "Invalid filename"}), 400

        if not _is_allowed(filename):
            ext = os.path.splitext(filename)[1].lower()
            return jsonify({"ok": False, "httpStatus": 400, "error": f"Unsupported file type: {ext}"}), 400

        # --- Create per-upload temp dir (preserve your existing PipelineState flow) ---
        tmpdir = tempfile.mkdtemp(prefix="fluidrag_")
        tmp_path = os.path.join(tmpdir, filename)
        f.save(tmp_path)

        def _sha256(path: str) -> str:
            h = hashlib.sha256()
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(8192), b""):
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()

        file_hash = _sha256(tmp_path)

        # --- Allocate a session id and store PipelineState (as your original code does) ---
        session_id = new_session_id()
        PIPELINE_STATES[session_id] = PipelineState(
            tmpdir=tmpdir,
            filename=filename,
            file_path=tmp_path,
            file_hash=file_hash,
        )
        log.debug("[upload] session=%s path=%s", session_id, tmp_path)

        # --- Normalize a stable path for downstream endpoints (/api/preprocess, headers, etc.) ---
        # Many routes look for uploads/<session>.pdf; keep that convention too.
        uploads_dir = getattr(config, "UPLOAD_FOLDER", None) or "uploads"
        os.makedirs(uploads_dir, exist_ok=True)
        # Force .pdf extension on normalized copy so later steps can find it deterministically
        norm_path = os.path.join(uploads_dir, f"{session_id}.pdf")
        try:
            shutil.copyfile(tmp_path, norm_path)
        except Exception as e:
            # If copy fails (e.g., non-PDF), we still return temp path;
            # but most of the pipeline expects a .pdf file.
            log.warning("Could not normalize upload to %s: %s", norm_path, e)
            norm_path = tmp_path

        # --- Response shape expected by the UI (uses 'session') ---
        cache_payload = load_document_cache(file_hash)
        cached_passes = sorted((cache_payload.get("passes") or {}).keys()) if isinstance(cache_payload, dict) else []
        payload = {
            "ok": True,
            "httpStatus": 200,
            "session": session_id,          # frontend logs "Upload ok. session=..."
            "session_id": session_id,       # keep for backward compatibility
            "filename": filename,
            "path": norm_path,              # deterministic path for subsequent calls
            "file_hash": file_hash,
            "cache": {
                "preprocess": bool(cache_payload.get("preprocess")) if isinstance(cache_payload, dict) else False,
                "headers": bool(cache_payload.get("headers")) if isinstance(cache_payload, dict) else False,
                "passes": cached_passes,
            },
        }
        resp = jsonify(payload)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp, 200

    except Exception as e:
        log.exception("Upload failed: %s", e)
        return jsonify({"ok": False, "httpStatus": 500, "error": str(e)}), 500
