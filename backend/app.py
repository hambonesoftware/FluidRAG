import asyncio
import io
import logging
import os
import tempfile
import time
import base64
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from dotenv import load_dotenv
load_dotenv()

from .pipeline.preprocess import load_document_to_text_pages, detect_headers_and_sections
from .pipeline.fluid import fluid_refine_chunks
from .pipeline.hep_cluster import hep_cluster_chunks
from .pipeline.llm import OpenRouterClient
from .pipeline.passes import run_all_passes_async
from .pipeline.csv_writer import rows_to_csv_bytes

# -------------- Logging --------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
log = logging.getLogger("FluidRAG")

# -------------- Flask App --------------
app = Flask(__name__, static_folder="../frontend", static_url_path="")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB
ALLOWED_EXT = {".pdf", ".docx", ".txt"}

# Models list (free-ish on OpenRouter; users may swap/extend as desired)
OPENROUTER_FREE_MODELS = [
    "deepseek/deepseek-chat:free",
    "mistralai/mistral-7b-instruct:free",
    "ollama/llama3.1-8b:free",
    "openchat/openchat-7b:free",
    "gryphe/mythomist-7b:free",
    "google/gemma-7b-it:free"
]

@app.get("/")
def index():
    # Serve the frontend
    return app.send_static_file("index.html")

@app.get("/api/models")
def get_models():
    log.debug("[API] /api/models")
    return jsonify({"ok": True, "models": OPENROUTER_FREE_MODELS})

@dataclass
class SectionChunk:
    document: str
    section_number: str
    section_name: str
    text: str
    meta: Dict[str, Any] = field(default_factory=dict)

@app.post("/api/process")
def process_file():
    """Upload a file and run the full pipeline, returning a CSV (base64) + rows."""
    ts0 = time.time()
    log.debug("[API] /api/process invoked")
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file provided"}), 400

    file = request.files["file"]
    model = request.form.get("model", OPENROUTER_FREE_MODELS[0])
    filename = secure_filename(file.filename or "upload")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"ok": False, "error": f"Unsupported file type: {ext}"}), 400

    tmpdir = tempfile.mkdtemp(prefix="fluidrag_")
    fpath = os.path.join(tmpdir, filename)
    file.save(fpath)
    log.debug(f"[API] Saved upload to {fpath}")

    # Step 1: Load and chunk pages
    log.debug("[STEP] load_document_to_text_pages")
    pages = load_document_to_text_pages(fpath)

    # Step 2: Detect headers/sections (regex + LLM assist)
    log.debug("[STEP] detect_headers_and_sections")
    sections = detect_headers_and_sections(pages)

    # Step 3: Fluid refinement (merge/split; target ~1-2k tokens equiv.)
    log.debug("[STEP] fluid_refine_chunks")
    refined = fluid_refine_chunks(sections)

    # Step 4: HEP clustering (entropy-based tf-idf seeding)
    log.debug("[STEP] hep_cluster_chunks")
    clustered = hep_cluster_chunks(refined)

    # Step 5: Async passes with OpenRouter
    log.debug("[STEP] run_all_passes_async")
    client = OpenRouterClient()
    results = asyncio.run(run_all_passes_async(clustered, client, model=model))
    llm_debug = client.drain_debug_records()

    # Step 6: Merge same specification text across passes
    merged = {}
    for r in results:
        key = (r["document"], r["section_number"], r["section_name"], r["specification"].strip())
        if key not in merged:
            merged[key] = {
                "Document": r["document"],
                "(Sub)Section #": r["section_number"],
                "(Sub)Section Name": r["section_name"],
                "Specification": r["specification"].strip(),
                "Pass": set([r["pass"]])
            }
        else:
            merged[key]["Pass"].add(r["pass"])
    rows = []
    for v in merged.values():
        v["Pass"] = "; ".join(sorted(list(v["Pass"])))
        rows.append(v)

    # Step 7: CSV
    csv_bytes = rows_to_csv_bytes(rows)
    b64 = base64.b64encode(csv_bytes).decode("utf-8")

    elapsed = round((time.time() - ts0)*1000, 1)
    log.debug(f"[DONE] Process complete in {elapsed} ms, rows={len(rows)}")

    return jsonify({
        "ok": True,
        "rows": rows,
        "csv_base64": b64,
        "filename": "FluidRAG_results.csv",
        "metrics_ms": {"total": elapsed},
        "llm_debug": llm_debug
    })

# Serve frontend assets
@app.get("/<path:asset>")
def static_proxy(asset):
    return app.send_static_file(asset)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5142))
    log.info(f"Starting FluidRAG on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
