# FluidRAG

A standalone RAG-style spec extractor with a Flask backend and ESM frontend. It implements a **standard → Fluid → HEP** text pipeline, then runs five parallel LLM passes (Mechanical, Electrical, Controls, Software, Project Management) to extract exact specification sentences. Results are merged and returned as a CSV.

Light-theme UI inspired by Microsoft 365 Copilot.

## Quick Start

```bash
# 1) Create and activate venv (Windows example)
py -3.12 -m venv .venv
.venv\Scripts\activate

# 2) Install backend deps
pip install -r backend/requirements.txt

# 3) Configure LLM endpoints
copy .env.example .env
# edit .env and set OPENROUTER_API_KEY (for OpenRouter)
# optionally set LLAMACPP_URL / LLAMACPP_MODELS / LLAMACPP_DEFAULT_MODEL for llama.cpp

# 4) Run the dev server
python run.py  # launches Flask + opens the frontend
```

> If `OPENROUTER_API_KEY` is missing, network calls short-circuit with mock outputs. Set the key for real OpenRouter calls.

## Guided workflow

1. **Upload & model selection**
   * Pick an LLM provider (OpenRouter cloud or your local llama.cpp endpoint) and then choose one of that provider's models.
   * Upload `.pdf`, `.docx`, or `.txt`. The backend stores the file in a session-scoped temp directory.
   * Optional “Test LLM” button exercises the selected provider using the legacy concatenated prompt format.

2. **Preprocess (standard chunking)**
   * Splits the raw document into overlapping ~4k-token coarse chunks.
   * Persists page strings for downstream steps.

3. **Determine headers**
   * Feeds the document to the selected provider in ≤120k-token slices.
   * Combines regex heading detection with LLM-confirmed headings to derive precise section/subsection spans.

4. **Fluid → HEP refinement**
   * Fluid pass merges/splits section chunks toward ~1–2k tokens.
   * HEP attaches entropy/cluster metadata for downstream weighting.

5. **Async passes & merge**
   * For each pass, chunks are ranked via entropy + domain keywords and truncated to a 120k-token budget before dispatching asynchronous calls to the selected provider.
   * Exact quoted specifications are deduplicated across passes. The merged result table is rendered in-app and offered as `FluidRAG_results.csv`.

## Configuration

* Update `backend/app.py` → `OPENROUTER_FREE_MODELS` to adjust the OpenRouter shortlist.
* Set `LLAMACPP_URL`, `LLAMACPP_MODELS`, and `LLAMACPP_DEFAULT_MODEL` (env vars) to point the llama.cpp client at your endpoint and preferred model aliases.
* Prompts live in `backend/prompts/__init__.py`.
* Frontend modules are standard ES Modules under `frontend/js/`.

## Dev containers / Codespaces

A ready-to-use dev container is included. In VS Code:

1. Install **Dev Containers** extension.
2. `File → Open Folder...` → choose this project.
3. When prompted, **Reopen in Container**.
4. Inside the container:
   ```bash
   pip install -r backend/requirements.txt
   python run.py
   ```

## License

MIT
