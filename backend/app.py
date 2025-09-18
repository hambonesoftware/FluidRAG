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

# Support running either as part of the backend package or as a direct script.
try:  # pragma: no cover - import resolution shim
    from backend.pipeline.preprocess import (
        load_document_to_text_pages,
        standard_pre_chunks,
        detect_headers_and_sections_async,
    )
    from backend.pipeline.fluid import fluid_refine_chunks
    from backend.pipeline.hep_cluster import hep_cluster_chunks
    from backend.pipeline.llm import (
        create_llm_client,
        LLMAuthError,
        provider_default_model,
    )
    from backend.pipeline.passes import run_all_passes_async
    from backend.pipeline.csv_writer import rows_to_csv_bytes
except ImportError:  # pragma: no cover - fallback when executed as package module
    from .pipeline.preprocess import (
        load_document_to_text_pages,
        standard_pre_chunks,
        detect_headers_and_sections_async,
    )
    from .pipeline.fluid import fluid_refine_chunks
    from .pipeline.hep_cluster import hep_cluster_chunks
    from .pipeline.llm import (
        create_llm_client,
        LLMAuthError,
        provider_default_model,
    )
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

_llamacpp_env = os.environ.get("LLAMACPP_MODELS", "")
if _llamacpp_env:
    LLAMACPP_MODELS = [m.strip() for m in _llamacpp_env.split(",") if m.strip()]
else:
    LLAMACPP_MODELS = [
        os.environ.get("LLAMACPP_DEFAULT_MODEL", "llama.cpp/default") or "llama.cpp/default"
    ]

DEFAULT_PROVIDER = "openrouter"
DEFAULT_MODEL = OPENROUTER_FREE_MODELS[0]
DEFAULT_LOCAL_MODEL = LLAMACPP_MODELS[0]

MODEL_PROVIDERS = {
    "openrouter": {
        "label": "OpenRouter",
        "models": OPENROUTER_FREE_MODELS,
        "default_model": DEFAULT_MODEL
    },
    "llamacpp": {
        "label": "llama.cpp",
        "models": LLAMACPP_MODELS,
        "default_model": DEFAULT_LOCAL_MODEL
    }
}


def _normalize_provider(value: Optional[str]) -> str:
    if not value:
        return DEFAULT_PROVIDER
    provider = value.strip().lower()
    return provider if provider in MODEL_PROVIDERS else DEFAULT_PROVIDER


def _resolve_model(provider: str, requested: Optional[str]) -> str:
    if requested:
        return requested
    env_default = provider_default_model(provider)
    if env_default:
        return env_default
    return MODEL_PROVIDERS[_normalize_provider(provider)]["default_model"]


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
    provider: Optional[str] = None


PIPELINE_STATES: Dict[str, PipelineState] = {}


@app.get("/")
def index():
    return app.send_static_file("index.html")


@app.get("/api/models")
def get_models():
    log.debug("[API] /api/models")
    return jsonify({
        "ok": True,
        "providers": MODEL_PROVIDERS,
        "default_provider": DEFAULT_PROVIDER
    })


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
    state = _get_state_or_404(session_id)
    if not state:
        return jsonify({"ok": False, "error": "Invalid session"}), 404
    provider = _normalize_provider(payload.get("provider") or state.provider)
    model = _resolve_model(provider, payload.get("model"))
    ts = time.time()
    pages = load_document_to_text_pages(state.file_path)
    pre_chunks = standard_pre_chunks(pages)
    state.pages = pages
    state.pre_chunks = pre_chunks
    state.model = model
    state.provider = provider
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
    state = _get_state_or_404(session_id)
    if not state:
        return jsonify({"ok": False, "error": "Invalid session"}), 404
    if not state.pages:
        return jsonify({"ok": False, "error": "Run preprocess first"}), 400
    provider = _normalize_provider(payload.get("provider") or state.provider)
    model = _resolve_model(provider, payload.get("model"))
    state.model = model
    state.provider = provider
    client = create_llm_client(provider)
    ts = time.time()
    try:
        section_chunks = asyncio.run(detect_headers_and_sections_async(state.pages, client, model))
    except LLMAuthError as exc:
        llm_debug = client.drain_debug_records()
        log.error("[API] header detection auth error (%s): %s", provider, exc)
        return jsonify({
            "ok": False,
            "error": str(exc),
            "needs_api_key": provider == "openrouter",
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
    state = _get_state_or_404(session_id)
    if not state:
        return jsonify({"ok": False, "error": "Invalid session"}), 404
    if not state.section_chunks:
        return jsonify({"ok": False, "error": "Determine headers before processing"}), 400
    provider = _normalize_provider(payload.get("provider") or state.provider)
    model = _resolve_model(provider, payload.get("model"))
    state.model = model
    state.provider = provider
    ts0 = time.time()
    log.debug("[API] process session=%s provider=%s model=%s", session_id, provider, model)

    refined = fluid_refine_chunks(state.section_chunks)
    clustered = hep_cluster_chunks(refined)
    state.refined_chunks = refined
    state.clustered_chunks = clustered

    client = create_llm_client(provider)
    try:
        rows_raw = asyncio.run(run_all_passes_async(clustered, client, model=model))
    except LLMAuthError as exc:
        llm_debug = client.drain_debug_records()
        log.error("[API] process auth error (%s): %s", provider, exc)
        return jsonify({
            "ok": False,
            "error": str(exc),
            "needs_api_key": provider == "openrouter",
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
    provider = _normalize_provider(payload.get("provider"))
    model = _resolve_model(provider, payload.get("model"))
    client = create_llm_client(provider)

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
    except LLMAuthError as exc:
        llm_debug = client.drain_debug_records()
        return jsonify({
            "ok": False,
            "error": str(exc),
            "needs_api_key": provider == "openrouter",
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
