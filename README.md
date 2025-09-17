# FluidRAG

A standalone RAG-style spec extractor with a Flask backend and ESM frontend.
It implements a **standard → Fluid → HEP** text pipeline, then runs five
parallel LLM passes (Mechanical, Electrical, Controls, Software, Project Management)
to extract exact specification sentences. Results are merged and returned as a CSV.

Light-theme UI inspired by M365 Copilot.

## Quick Start

```bash
# 1) Create and activate venv (Windows example)
py -3.12 -m venv .venv
.venv\Scripts\activate

# 2) Install backend deps
pip install -r backend/requirements.txt

# 3) Configure API key
copy .env.example .env
# edit .env and set OPENROUTER_API_KEY

# 4) Run
python backend/app.py

# 5) Open
# http://127.0.0.1:5142/
```

> If `OPENROUTER_API_KEY` is missing, the app runs with deterministic mock
> outputs (no real extraction). Set the key for real LLM calls.

## How it works

1. **Preprocess**
   * Load `.pdf`, `.docx`, or `.txt`
   * Detect section headings via regex heuristics (`1`, `1.1`, etc.).
   * Segment text into section-bounded chunks.

2. **Fluid Refinement**
   * Merge very short chunks, split very long ones using overlaps to aim
     for ~1-2k token equivalents.

3. **HEP Clustering**
   * TF‑IDF features + k‑means.
   * Attach `cluster_id` and a simple entropy score to each chunk.

4. **Async Passes**
   * For each chunk, run 5 extraction passes concurrently via OpenRouter.
   * Each pass returns a JSON array of **exact quotations** matching domain criteria.

5. **Merge & CSV**
   * Combine identical `"Specification"` strings across passes into a single row.
   * `"Pass"` becomes a semicolon‑separated list.

## Configuration

* Edit `backend/app.py` → `OPENROUTER_FREE_MODELS` to change the default model list.
* Prompts live in `backend/prompts/__init__.py`. Tweak to your liking.

## GitHub Codespaces / Dev Containers

A ready-to-use dev container is included. In VS Code:

1. Install **Dev Containers** extension.
2. `File → Open Folder...` → choose this project.
3. When prompted, **Reopen in Container**.
4. Inside the container:
   ```bash
   pip install -r backend/requirements.txt
   python backend/app.py
   ```

## License

MIT
