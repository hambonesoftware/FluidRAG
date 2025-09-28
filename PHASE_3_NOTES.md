# Phase 3 Notes — Upload & Parser Fan-Out/Fan-In

## Overview
- Added upload normalization service with validation guards, PDF-to-JSON normalization, OCR fallback, and manifest emission.
- Added parser service with asyncio fan-out (text, tables, images, links, language) and merge layer producing `parse.enriched.json`.
- Exposed `/upload/normalize` and `/parser/enrich` routes in FastAPI and wired new settings for artifact storage and parser timeout.
- Delivered benchmark harness (`scripts/bench_phase3.py`) to measure offline latency of the upload→parser pipeline.

## Configuration
- `ARTIFACT_ROOT` (default `rag-app/data/artifacts`): directory root for `normalize.json` and `parse.enriched.json` artifacts.
- `UPLOAD_OCR_THRESHOLD` (default `0.85`): minimum average coverage before OCR fallback mutates pages.
- `PARSER_TIMEOUT_SECONDS` (default `1.0`): timeout per parser task in seconds.

## Running the Pipeline
1. Launch the backend: `python run.py` from `rag-app/`.
2. Normalize content:
   ```bash
   curl -s -X POST http://127.0.0.1:8000/upload/normalize \
     -H 'Content-Type: application/json' \
     -d '{"file_id": "Sample text with [image:diagram] and https://example.com"}'
   ```
3. Parse and enrich using the returned `doc_id` and `normalize.json` path:
   ```bash
   curl -s -X POST http://127.0.0.1:8000/parser/enrich \
     -H 'Content-Type: application/json' \
     -d '{"doc_id": "<doc_id>", "normalize_artifact": "<normalize_path>"}'
   ```
4. Inspect `${ARTIFACT_ROOT}/<doc_id>/parse.enriched.json` for merged output.

## Tests & Quality Gates
- Linting/formatting: `ruff check --fix rag-app`, `BLACK_CACHE_DIR=/tmp/black-cache black rag-app`, `ruff check rag-app`, `black --check rag-app`.
- Offline test suite: `FLUIDRAG_OFFLINE=true pytest -q -o cache_dir=/tmp/pytest_cache` (24 passed).

## Benchmark
Executed `python rag-app/scripts/bench_phase3.py --iterations 5` offline:
- Upload p50: 1.0 ms, p95: 1.7 ms
- Parser p50: 6.4 ms, p95: 12.5 ms
- Total p50: 7.4 ms, p95: 14.1 ms

## Migrations
- No database migrations required; artifacts are stored on disk. Ensure `${ARTIFACT_ROOT}` exists and is writable.

## Back-Compat
- Existing Phase 1 & 2 tests remain green under the offline matrix. Routes and settings preserve defaults for prior features.
