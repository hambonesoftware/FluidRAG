# FluidRAG — Phase 1 Foundations

This repository currently contains the Phase 1 foundations for the FluidRAG project. The goal of this phase is to provide a reproducible development environment with:

- A FastAPI backend that boots through `python run.py`.
- A static frontend served from the same command for quick smoke tests.
- Shared tooling (`black`, `ruff`, `pytest`, pre-commit) to keep the codebase healthy.

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp rag-app/.env.example rag-app/.env
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

All three commands are also wired into the `pre-commit` configuration along with a guard that fails when any source file exceeds 500 lines.

## Configuration

The application reads environment variables via `backend.app.config.Settings`. Copy `.env.example` to `.env` to override defaults for ports, reload mode, logging level, or the offline policy.

- `FLUIDRAG_OFFLINE` (default: `true`) prevents any outbound network traffic when enabled. Set it to `false` in `.env` if you need to permit integrations that reach external services.

## Next Steps

Future phases will flesh out the service routes, adapters, and frontend MVVM components. The current foundation keeps that expansion ready by providing shared utilities, structured logging, and resilience helpers.
