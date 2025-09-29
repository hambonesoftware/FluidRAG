# FluidRAG — Release Readiness

FluidRAG is a FastAPI-powered retrieval-augmented generation pipeline with an MVVM
frontend, OpenRouter client, hybrid retrieval, and deterministic offline harness.
Phase 11 focuses on documentation, handover tooling, and a smooth release workflow
while preserving the architecture and behaviours delivered in phases 1–10.

## Quickstart

```bash
cd rag-app
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
pre-commit install
python run.py  # FastAPI on :8000, static frontend on :3000
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000) to access the dashboard. The
frontend exposes upload controls, pipeline status polling, and pass result views
with offline-aware messaging.

To verify release readiness end-to-end, run the scripted checklist:

```bash
python scripts/release_checklist.py
```

A zero exit code indicates all required docs and scripts are present.

## Environment Setup

All configuration is driven by `backend.app.config.Settings`. Copy `.env.example`
into `.env` and customise as needed.

### Core runtime toggles

- `FLUIDRAG_OFFLINE` — defaults to `true` to disable outbound network calls.
- `ARTIFACT_ROOT` — where the pipeline writes manifests and audit artifacts.
- `BACKEND_HOST`/`BACKEND_PORT` — FastAPI bind address (default `127.0.0.1:8000`).
- `FRONTEND_PORT` — static site port (default `3000`).
- `LOG_LEVEL` — log verbosity for the shared `fluidrag` logger.

### Ingestion & retrieval knobs

- `UPLOAD_OCR_THRESHOLD` — coverage threshold before OCR fallback.
- `PARSER_TIMEOUT_SECONDS` — timeout per parser fan-out task.
- `CHUNK_TARGET_TOKENS` / `CHUNK_TOKEN_OVERLAP` — UF chunk sizing.
- `VECTOR_BATCH_SIZE` / `LLM_BATCH_SIZE` — offline batching controls.
- `AUDIT_RETENTION_DAYS` — retention window for stage audit artifacts.
- `STORAGE_STREAM_CHUNK_SIZE` — streaming chunk size for artifact downloads.

### OpenRouter integration

Set these when `FLUIDRAG_OFFLINE=false`:

- `OPENROUTER_API_KEY`
- `OPENROUTER_HTTP_REFERER`
- `OPENROUTER_APP_TITLE`
- `OPENROUTER_BASE_URL` (optional override)
- `OPENROUTER_TIMEOUT_SECONDS`, `OPENROUTER_MAX_RETRIES`,
  `OPENROUTER_BACKOFF_BASE_SECONDS`, `OPENROUTER_BACKOFF_CAP_SECONDS`, and
  `OPENROUTER_STREAM_IDLE_TIMEOUT_SECONDS` for retry/backoff control.

## Running the Pipeline

### Offline demo script

Use the curated engineering document shipped with the test fixtures to trigger
the orchestrator without external dependencies:

```bash
python - <<'PY'
from pathlib import Path
source = Path('backend/app/tests/data/documents/engineering_overview.txt')
target = Path('backend/app/tests/data/tmp/engineering_overview.pdf')
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(source.read_text(encoding='utf-8'), encoding='utf-8')
print(target)
PY

python scripts/offline_pipeline_demo.py backend/app/tests/data/tmp/engineering_overview.pdf --json
```

The demo script calls `/pipeline/run`, polls `/pipeline/status/{doc_id}` until the
audit reports success, and finally fetches `/pipeline/results/{doc_id}`. The JSON
payload includes the manifest, audit envelope, and pass metadata for downstream
inspection.

### Manual API calls

When the backend is running you can interact with the services directly:

```bash
# Normalize content
curl -s -X POST http://127.0.0.1:8000/upload/normalize \
  -H 'Content-Type: application/json' \
  -d '{"file_id": "Sample document text with [image:diagram] and https://example.com"}'

# Parser enrichment
curl -s -X POST http://127.0.0.1:8000/parser/enrich \
  -H 'Content-Type: application/json' \
  -d '{"doc_id": "<doc_id>", "normalize_artifact": "<normalize_path>"}'

# Chunking
curl -s -X POST http://127.0.0.1:8000/chunk/uf \
  -H 'Content-Type: application/json' \
  -d '{"doc_id": "<doc_id>", "normalize_artifact": "<parse_enriched_path>"}'

# Pipeline orchestrator
curl -s -X POST http://127.0.0.1:8000/pipeline/run \
  -H 'Content-Type: application/json' \
  -d '{"file_name": "<path-or-handle-to-source>"}'

# Status and results
curl -s http://127.0.0.1:8000/pipeline/status/<doc_id>
curl -s http://127.0.0.1:8000/pipeline/results/<doc_id>

# Stream an artifact (guards ensure paths stay within ARTIFACT_ROOT)
curl -s -G http://127.0.0.1:8000/pipeline/artifacts --data-urlencode "path=<artifact>" -o artifact.json
```

Artifacts, manifests, and pass payloads live beneath `ARTIFACT_ROOT` (defaults to
`data/artifacts`).

## Quality Gates

Run these from the repository root (`rag-app/`) before cutting a release:

```bash
pytest -q --maxfail=1 --disable-warnings
pytest --cov=backend/app --cov-report=term-missing
mypy backend/app --pretty --show-error-codes
ruff check backend/app tests --fix
ruff format backend/app tests
python scripts/release_checklist.py --json
```

Node-based frontend tests live under `tests/phase_8`; `pytest.ini` ensures they
run alongside backend suites when Node.js is available (Node 20+ recommended).

## Troubleshooting

- **`node` not found during frontend tests** — install Node.js 18+ and ensure it
  is on your `PATH`. The CI image uses Node 20.
- **`document not found` when running the demo script** — create the pseudo-PDF
  using the snippet above or provide an absolute path to an accessible file.
- **Offline mode blocking external calls** — leave `FLUIDRAG_OFFLINE=true` during
  tests. Set it to `false` only when ready to hit OpenRouter with valid headers.
- **Artifacts missing** — verify `ARTIFACT_ROOT` points to a writable location and
  that the backend has permission to create directories.
- **Coverage shortfalls** — ensure new modules include targeted tests under
  `backend/app/tests` or `tests/phase_11/` before re-running quality gates.

## Observability & Profiling

The backend emits structured JSON logs with correlation IDs and span durations.
Each pipeline stage writes audit records (`pipeline.audit.json`) capturing
per-stage timings. Use `jq` or log aggregators to analyse runtime behaviour.

## Release Tooling & Reports

- `scripts/release_checklist.py` — validates docs, templates, and backlog files.
  Use `--json` for machine-readable output or `--root` to target alternative
  directories.
- `scripts/offline_pipeline_demo.py` — drives the orchestrator endpoints end-to-end
  for smoke testing and demonstrations.
- `reports/phase_11_outcome.md` — summarises checklist completion, quality gates,
  and migration status for this phase.
- `reports/post_phase_backlog.md` — triaged backlog of enhancements to consider
  after release (e.g., UI polish, additional retrieval metrics, deployment work).

## Frontend MVVM Dashboard

The dashboard remains fully offline-aware:

- **Upload panel** — triggers `/pipeline/run`, persists the last `doc_id`, and
  surfaces validation errors inline.
- **Pipeline monitor** — polls `/pipeline/status/{doc_id}` and
  `/pipeline/results/{doc_id}` until the pipeline completes, updating progress and
  timestamps live.
- **Results view** — renders pass answers, citations, and artifact links while
  respecting offline mode. Download actions dispatch DOM events for analytics.

Reloading the page restores the most recent document and resumes polling as long
as the backend remains reachable.

## Additional Resources

- `CHANGELOG.md` — release history with phase-by-phase summaries.
- `reports/phase_*` — historical outcome and verification reports.
- `scripts/bench_phase3.py` — micro-benchmark harness for upload and parser stages.
- `backend/app/tests/` — exhaustive unit, integration, and e2e coverage for the
  pipeline services and routes.
