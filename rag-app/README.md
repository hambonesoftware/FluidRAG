# FluidRAG — Phases 1 & 2 Foundations

Phase 1 established the project skeleton (tooling, boot scripts, static frontend). Phase 2 adds a production-ready OpenRouter client with retry logic, structured streaming, and embedding support while preserving the offline-first defaults.

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pre-commit install
python run.py  # launches FastAPI on :8000 and static frontend on :3000
```

Open [http://localhost:3000](http://localhost:3000) to load the static shell and ping the backend health endpoint.

## Testing & Linting

```bash
ruff check .
black --check .
pytest -q
```

All three commands are wired into the `pre-commit` configuration along with a guard that fails when any source file exceeds 500 lines.

## Configuration

The application reads environment variables via `backend.app.config.Settings`. Copy `.env.example` to `.env` to override defaults for ports, reload mode, logging level, or the offline policy.

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
