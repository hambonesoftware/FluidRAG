Phase 1 established the project skeleton (tooling, boot scripts, static frontend). Phase 2 adds a production-ready OpenRouter client with retry logic, structured streaming, and embedding support while preserving the offline-first defaults. Phase 3 introduces the upload normalization + parser fan-out/fan-in services, FastAPI routes, and an offline benchmark harness. Phase 7 wires the orchestrator API layer so the entire pipeline can be triggered and inspected through dedicated routes.

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pre-commit install
python run.py  # launches FastAPI on :8000 and static frontend on :3000
```

Open [http://localhost:3000](http://localhost:3000) to load the frontend dashboard, trigger pipeline runs, monitor progress, and download artifacts.

## Upload & Parser Pipeline

With the backend running:

```bash
curl -s -X POST http://127.0.0.1:8000/upload/normalize \
  -H 'Content-Type: application/json' \
  -d '{"file_id": "Sample document text with [image:diagram] and https://example.com"}'
```

The response includes the generated `doc_id`, `normalize.json` path, and manifest. Feed that artifact into the parser:

```bash
curl -s -X POST http://127.0.0.1:8000/parser/enrich \
  -H 'Content-Type: application/json' \
  -d '{"doc_id": "<doc_id>", "normalize_artifact": "<normalize_path>"}'
```

This triggers the asyncio fan-out (text/tables/images/links/language) and fan-in merge, producing `parse.enriched.json` under the artifact root.

## Chunk Service & Vector Indexes

After running the parser, invoke the chunk service to generate UF chunks and build local indexes:

```bash
curl -s -X POST http://127.0.0.1:8000/chunk/uf \
  -H 'Content-Type: application/json' \
  -d '{"doc_id": "<doc_id>", "normalize_artifact": "<parse_enriched_path>"}'
```

The response echoes the chunk artifact path (`uf_chunks.jsonl`) and, if enabled, the index manifest. The chunk controller writes a `chunk.audit.json` record alongside the JSONL file and persists sparse+dense index metadata when offline-safe hashing is enabled by default.

## Pipeline Orchestrator & Artifact Access

With Phase 7 the orchestrator coordinates every stage:

```bash
curl -s -X POST http://127.0.0.1:8000/pipeline/run \
  -H 'Content-Type: application/json' \
  -d '{"file_name": "<path-or-handle-to-source>"}'
```

The response bundles the normalized, parsed, chunked, header-joined, and pass metadata along with the audit record location written to `<ARTIFACT_ROOT>/<doc_id>/pipeline.audit.json`.

Query the aggregated status for a document (manifest snapshot + audit trail):

```bash
curl -s http://127.0.0.1:8000/pipeline/status/<doc_id>
```

Fetch the pass manifest and fully validated pass payloads:

```bash
curl -s http://127.0.0.1:8000/pipeline/results/<doc_id>
```

Artifacts can be streamed back without loading them into memory. The route enforces that all paths stay within the configured `ARTIFACT_ROOT`.

```bash
curl -s -G http://127.0.0.1:8000/pipeline/artifacts --data-urlencode "path=<absolute-or-relative-artifact>" -o artifact.json
```

## Frontend MVVM Dashboard

- **Upload panel** — enter a path or document identifier and click **Run Pipeline**. The upload view-model persists the most recent `doc_id` in `localStorage` and surfaces job errors inline.
- **Pipeline monitor** — the dashboard polls `/pipeline/status/{doc_id}` and `/pipeline/results/{doc_id}` until the audit record reports completion. Progress, last updated timestamps, and the active document id are shown in real time.
- **Pass results** — each pass renders its answer, citation list, and top retrieval traces. Download buttons call `/pipeline/artifacts` while respecting the offline flag.
- **Offline mode** — when the `<meta name="fluidrag-offline">` flag is `true`, the UI short-circuits network calls and emits banner messaging while still allowing users to explore previously cached results.

Reloading the page restores the last processed document and resumes polling automatically as long as offline mode remains disabled.

## Benchmark Harness

To measure offline performance end-to-end:

```bash
python rag-app/scripts/bench_phase3.py --iterations 5
```

The script reports p50/p95 latencies for upload, parser, and combined stages while respecting the offline flag.

## Testing & Linting

```bash
ruff check .
black --check .
pytest -q
```

All three commands are wired into the `pre-commit` configuration along with a guard that fails when any source file exceeds 500 lines.

## Configuration

The application reads environment variables via `backend.app.config.Settings`. Copy `.env.example` to `.env` to override defaults for ports, reload mode, logging level, or the offline policy.

Key variables for the ingestion pipeline:

- `ARTIFACT_ROOT` — directory where `normalize.json` and `parse.enriched.json` are written (defaults to `rag-app/data/artifacts`).
- `UPLOAD_OCR_THRESHOLD` — minimum average coverage (0–1) before the upload controller triggers OCR fallback.
- `PARSER_TIMEOUT_SECONDS` — timeout applied to each parser fan-out task.
- `CHUNK_TARGET_TOKENS` — target token count for each UF chunk (defaults to 90).
- `CHUNK_TOKEN_OVERLAP` — token overlap budget between adjacent chunks (defaults to 12).

Key variables for the OpenRouter integration:

- `FLUIDRAG_OFFLINE` (default: `true`) prevents any outbound network traffic when enabled. Leave it `true` for local unit testing; flip to `false` only when you are ready to hit OpenRouter.
- `OPENROUTER_API_KEY` — required bearer token for OpenRouter requests.
- `OPENROUTER_HTTP_REFERER` — URL of the site/project registered with OpenRouter.
- `OPENROUTER_APP_TITLE` — human-readable name sent in the `X-Title` header.
- `OPENROUTER_BASE_URL` — optional override for the API endpoint (defaults to `https://openrouter.ai/api/v1`).

## OpenRouter Client Smoke Test

1. Ensure `FLUIDRAG_OFFLINE=false` in your local `.env` and populate the OpenRouter headers listed above.
2. Run the quick chat smoke test (streams tokens to stdout):

   ```bash
   python - <<'PY'
   import asyncio
   from backend.app.llm.clients.openrouter import chat_stream_async

   async def main() -> None:
       async for chunk in chat_stream_async(
           "openrouter/auto",
           [{"role": "user", "content": "Say hello to FluidRAG"}],
           temperature=0.2,
           retries=1,
       ):
           if chunk["type"] == "delta":
               content = chunk["data"].get("delta", {}).get("content")
               if content:
                   print(content, end="", flush=True)
   asyncio.run(main())
   PY
   ```

3. To test embeddings offline, run `pytest -q` which exercises the retry, masking, and idle timeout handling without real network calls.

## Next Steps

Future phases will flesh out the service routes, adapters, and frontend MVVM components. With the OpenRouter client in place, downstream services can rely on deterministic retries, masked logging, and streaming primitives without duplicating integration logic.
