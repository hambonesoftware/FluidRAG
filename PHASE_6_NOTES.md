# Phase 6 delivery notes

## Overview
- Added orchestration routes for running the full pipeline, retrieving status, streaming artifacts, and exposing pass results.
- Implemented the RAG pass service with hybrid retrieval, physics-inspired ranking, context composition, prompt templates, and JSON emitters.
- Introduced storage/LLM/DB adapters and new contracts to support pass execution and artifact manifests.
- Built unit, contract, and e2e tests covering retrieval ranking, pass persistence, manifest schemas, and the orchestrator API (with upstream services stubbed for isolation).
- Delivered frontend MVVM assets (API client, models, view models, and views) plus UI wiring to trigger pipeline runs and inspect results.

## Running the pipeline locally
1. Ensure dependencies are installed: `python -m pip install -r rag-app/requirements.txt`.
2. Export `FLUIDRAG_OFFLINE=true` to stay offline by default.
3. Launch the backend: `uvicorn backend.app.main:create_app --factory --reload`.
4. Open `rag-app/frontend/index.html` with a static server (e.g. `python -m http.server 3000 -d rag-app/frontend`).
5. Enter a document path (or reuse an existing artifact id) and trigger **Run Pipeline**; use **Refresh Results** to reload emitted pass JSON.

## Tests executed
- `ruff check rag-app`
- `black --check rag-app`
- `FLUIDRAG_OFFLINE=true pytest -q -o cache_dir=/tmp/pytest_cache`

## Offline/online behaviour
- All new adapters inspect `FLUIDRAG_OFFLINE`; in offline mode the LLM adapter synthesises deterministic completions and embeddings without network calls.
- The API client short-circuits fetches when the offline meta flag is present, surfacing offline status in the UI.

## Artifacts & outputs
- Pass results are written to `<artifact_root>/<doc_id>/passes/<pass>.json` with an accompanying `manifest.json` and audit log (`passes.audit.json`).
- Orchestrator status reads from `document.manifest.json` and the pass manifest to present pipeline stage progress.
- Frontend renders pass answers, citations, and retrieval summaries.

## Migration & compatibility
- No database migrations required. Existing Phase 1–5 services remain untouched; orchestrator routes wrap the prior service interfaces.
- New adapters remain backward compatible and are only consumed by the RAG pass flow.
