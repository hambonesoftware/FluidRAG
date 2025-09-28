# Phase 2 — OpenRouter Client Integration

## Summary
- Added OpenRouter utility modules (`backend/app/llm/utils.py`, `utils/envsafe.py`) for header masking, logging metadata, and Windows-friendly `curl` output.
- Implemented the full OpenRouter client (`backend/app/llm/clients/openrouter.py`) with sync chat, async streaming, and embeddings plus jittered retries and idle timeout handling.
- Created a thin wrapper in `backend/app/llm/openrouter.py` for downstream synchronous callers.
- Expanded unit coverage with offline-safe tests for env helpers, retry logic, streaming, and embeddings.
- Updated developer docs and `.env.example` with the new configuration knobs and smoke-test recipe.

## Running Tests & Tooling
```bash
ruff --fix
ruff check
BLACK_CACHE_DIR=/tmp/black-cache black
black --check
FLUIDRAG_OFFLINE=true pytest -q
```

All tests mock outbound HTTP and respect the offline flag by default.

## Configuration Checklist
- Set `FLUIDRAG_OFFLINE=false` only when you intend to hit OpenRouter.
- Populate `OPENROUTER_API_KEY`, `OPENROUTER_HTTP_REFERER`, and `OPENROUTER_APP_TITLE` in your local `.env` before running the smoke test or live requests.
- Optional: override `OPENROUTER_BASE_URL` if targeting a mock server.

## Known Limitations / Follow-ups
- No live integration test is wired yet; future phases may add contract tests once the orchestrator routes exist.
- Streaming output currently emits generic `delta` and `done` events; downstream consumers can enrich this schema once pipeline requirements are finalised.
