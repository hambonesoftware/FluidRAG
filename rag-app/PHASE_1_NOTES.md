# Phase 1 Notes — FluidRAG Foundations

## Summary
- Implemented FastAPI app factory (`backend/app/main.py`) with health endpoint and startup/shutdown logging.
- Added environment-driven `Settings` with cached accessor plus structured logging, audit helpers, retry utilities, and common errors.
- Created `run.py` launcher to boot backend and static frontend concurrently via multiprocessing.
- Delivered static frontend shell with health check button and gradient styling.
- Established tooling: requirements, `pyproject.toml` with `black` + `ruff`, pre-commit hook enforcing 500-line policy, and baseline tests.

## Running the Stack
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py  # backend on :8000, frontend on :3000
```

When running inside a container or remote workspace where the preview needs to
be accessed from another process (for example, Playwright-driven screenshots),
export the host bindings first:

```bash
FRONTEND_HOST=0.0.0.0 BACKEND_HOST=0.0.0.0 python run.py
```

## Testing
```bash
pytest -q
```

## Environment
- Copy `.env.example` to `.env` within `rag-app` to customize runtime settings without committing secrets.
- `FLUIDRAG_OFFLINE` defaults to `true` to disable outbound network calls; flip to `false` when integrations require external access.

## Offline Mode
- Backend: `backend.app.config.Settings.offline` exposes the offline flag for service and client guards.
- Frontend: `index.html` ships with a `fluidrag-offline` meta tag, and `main.js` bypasses the health check fetch (with an inline notice) while offline.

## Tooling
- `pre-commit install` to enable ruff, black, and file-length guard.
- `ruff check .` / `black --check .` for standalone linting/formatting verification.

## Known Limitations
- Domain services, orchestrator routes, and MVVM frontend layers are deferred to later phases.
- `run.py` currently expects local execution; production-grade process supervision will be added alongside deployment work.
