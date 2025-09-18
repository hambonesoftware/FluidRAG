import asyncio
import base64
import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

from dotenv import load_dotenv
load_dotenv()

from .pipeline.preprocess import (
    load_document_to_text_pages,
    standard_pre_chunks,
    detect_headers_and_sections_async
)
from .pipeline.fluid import fluid_refine_chunks
from .pipeline.hep_cluster import hep_cluster_chunks
from .pipeline.llm import OpenRouterClient, OpenRouterAuthError
from .pipeline.passes import run_all_passes_async
from .pipeline.csv_writer import rows_to_csv_bytes

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("FluidRAG")

app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
ALLOWED_EXT = {".pdf", ".docx", ".txt"}

OPENROUTER_FREE_MODELS = [
    "deepseek/deepseek-chat:free",
    "deepseek/deepseek-r1:free",
    "mistralai/mistral-7b-instruct:free",
    "mistralai/mixtral-8x7b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "ollama/llama3.1-8b:free",
    "qwen/qwen-2.5-7b-instruct:free",
    "openchat/openchat-7b:free",
    "gryphe/mythomist-7b:free",
    "google/gemma-7b-it:free"
]
DEFAULT_MODEL = OPENROUTER_FREE_MODELS[0]


@dataclass
class PipelineState:
    tmpdir: str
    filename: str
    file_path: str
    pages: Optional[List[str]] = None
    pre_chunks: Optional[List[Dict[str, Any]]] = None
    section_chunks: Optional[List[Dict[str, Any]]] = None
    refined_chunks: Optional[List[Dict[str, Any]]] = None
    clustered_chunks: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = None


PIPELINE_STATES: Dict[str, PipelineState] = {}


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/models")
def get_models():
    log.debug("[API] /api/models")
    return jsonify({"ok": True, "models": OPENROUTER_FREE_MODELS})


def _get_state_or_404(session_id: str) -> Optional[PipelineState]:
    state = PIPELINE_STATES.get(session_id)
    if not state:
        return None
    return state


@app.post("/api/upload")
def upload_file():
    log.debug("[API] /api/upload invoked")
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file provided"}), 400
    file = request.files["file"]
    filename = secure_filename(file.filename or "upload")
    if not filename:
        return jsonify({"ok": False, "error": "Invalid filename"}), 400
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"ok": False, "error": f"Unsupported file type: {ext}"}), 400
    tmpdir = tempfile.mkdtemp(prefix="fluidrag_")
    fpath = os.path.join(tmpdir, filename)
    file.save(fpath)
    session_id = uuid.uuid4().hex
    PIPELINE_STATES[session_id] = PipelineState(tmpdir=tmpdir, filename=filename, file_path=fpath)
    log.debug("[API] upload stored session=%s path=%s", session_id, fpath)
    return jsonify({"ok": True, "session_id": session_id, "filename": filename})


@app.post("/api/preprocess")
def preprocess_document():
    payload = request.get_json(force=True)
    session_id = payload.get("session_id")
    model = payload.get("model", DEFAULT_MODEL)
    state = _get_state_or_404(session_id)
    if not state:
        return jsonify({"ok": False, "error": "Invalid session"}), 404
    ts = time.time()
    pages = load_document_to_text_pages(state.file_path)
    pre_chunks = standard_pre_chunks(pages)
    state.pages = pages
    state.pre_chunks = pre_chunks
    state.model = model
    elapsed = round((time.time() - ts) * 1000, 1)
    log.debug("[API] preprocess pages=%s chunks=%s", len(pages), len(pre_chunks))
    return jsonify({
        "ok": True,
        "pages": len(pages),
        "pre_chunks": len(pre_chunks),
        "metrics_ms": {"preprocess": elapsed}
    })


@app.post("/api/determine-headers")
def determine_headers():
    payload = request.get_json(force=True)
    session_id = payload.get("session_id")
    model = payload.get("model") or DEFAULT_MODEL
    state = _get_state_or_404(session_id)
    if not state:
        return jsonify({"ok": False, "error": "Invalid session"}), 404
    if not state.pages:
        return jsonify({"ok": False, "error": "Run preprocess first"}), 400
    state.model = model
    client = OpenRouterClient()
    ts = time.time()
    try:
        section_chunks = asyncio.run(detect_headers_and_sections_async(state.pages, client, model))
    except OpenRouterAuthError as exc:
        llm_debug = client.drain_debug_records()
        log.error("[API] header detection auth error: %s", exc)
        return jsonify({
            "ok": False,
            "error": str(exc),
            "needs_api_key": True,
            "llm_debug": llm_debug
        }), 401
    except Exception as exc:
        llm_debug = client.drain_debug_records()
        log.exception("[API] header detection failed")
        return jsonify({"ok": False, "error": str(exc), "llm_debug": llm_debug}), 500
    llm_debug = client.drain_debug_records()
    state.section_chunks = section_chunks
    elapsed = round((time.time() - ts) * 1000, 1)
    preview = [
        {
            "section_number": ch["section_number"],
            "section_name": ch["section_name"],
            "chars": len(ch["text"])
        }
        for ch in section_chunks[:5]
    ]
    return jsonify({
        "ok": True,
        "sections": len(section_chunks),
        "preview": preview,
        "metrics_ms": {"headers": elapsed},
        "llm_debug": llm_debug
    })


@app.post("/api/process")
def process_pipeline():
    payload = request.get_json(force=True)
    session_id = payload.get("session_id")
    model = payload.get("model") or DEFAULT_MODEL
    state = _get_state_or_404(session_id)
    if not state:
        return jsonify({"ok": False, "error": "Invalid session"}), 404
    if not state.section_chunks:
        return jsonify({"ok": False, "error": "Determine headers before processing"}), 400
    state.model = model
    ts0 = time.time()
    log.debug("[API] process session=%s model=%s", session_id, model)

    refined = fluid_refine_chunks(state.section_chunks)
    clustered = hep_cluster_chunks(refined)
    state.refined_chunks = refined
    state.clustered_chunks = clustered

    client = OpenRouterClient()
    try:
        rows_raw = asyncio.run(run_all_passes_async(clustered, client, model=model))
    except OpenRouterAuthError as exc:
        llm_debug = client.drain_debug_records()
        log.error("[API] process auth error: %s", exc)
        return jsonify({
            "ok": False,
            "error": str(exc),
            "needs_api_key": True,
            "llm_debug": llm_debug
        }), 401
    rows_merged: Dict[Any, Dict[str, Any]] = {}
    for r in rows_raw:
        key = (
            r["document"],
            r["section_number"],
            r["section_name"],
            r["specification"].strip()
        )
        if key not in rows_merged:
            rows_merged[key] = {
                "Document": r["document"],
                "(Sub)Section #": r["section_number"],
                "(Sub)Section Name": r["section_name"],
                "Specification": r["specification"].strip(),
                "Pass": {r["pass"]}
            }
        else:
            rows_merged[key]["Pass"].add(r["pass"])
    rows = []
    for value in rows_merged.values():
        value["Pass"] = "; ".join(sorted(list(value["Pass"])))
        rows.append(value)

    csv_bytes = rows_to_csv_bytes(rows)
    b64 = base64.b64encode(csv_bytes).decode("utf-8")
    elapsed = round((time.time() - ts0) * 1000, 1)
    llm_debug = client.drain_debug_records()
    log.debug("[DONE] Process session=%s rows=%s ms=%s", session_id, len(rows), elapsed)
    return jsonify({
        "ok": True,
        "rows": rows,
        "csv_base64": b64,
        "filename": "FluidRAG_results.csv",
        "metrics_ms": {"total": elapsed},
        "llm_debug": llm_debug
    })


@app.post("/api/llm-test")
def llm_test():
    payload = request.get_json(force=True, silent=True) or {}
    model = payload.get("model") or DEFAULT_MODEL
    client = OpenRouterClient()

    async def _probe():
        system = "You validate connectivity for FluidRAG."
        user = (
            "Respond with JSON {\"status\": \"ok\", \"message\": \"FluidRAG connectivity confirmed\"}. "
            "No additional text."
        )
        return await client.acomplete(model=model, system=system, user=user, temperature=0.0, max_tokens=120)

    try:
        content = asyncio.run(_probe())
        parsed = json.loads(content)
    except OpenRouterAuthError as exc:
        llm_debug = client.drain_debug_records()
        return jsonify({
            "ok": False,
            "error": str(exc),
            "needs_api_key": True,
            "llm_debug": llm_debug
        }), 401
    except json.JSONDecodeError:
        llm_debug = client.drain_debug_records()
        return jsonify({
            "ok": False,
            "error": "LLM returned non-JSON response",
            "llm_debug": llm_debug,
            "raw": content
        }), 502
    except Exception as exc:
        llm_debug = client.drain_debug_records()
        log.exception("[API] LLM test failed")
        return jsonify({"ok": False, "error": str(exc), "llm_debug": llm_debug}), 500

    llm_debug = client.drain_debug_records()
    return jsonify({"ok": True, "response": parsed, "llm_debug": llm_debug})


@app.get("/<path:asset>")
def static_proxy(asset):
    return app.send_static_file(asset)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5142))
    log.info(f"Starting FluidRAG on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
