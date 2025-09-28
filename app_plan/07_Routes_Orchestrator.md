# Phase 7 — API Routes & Orchestrator

## Goals
- Wire a clean API: orchestrate pipeline; stream artifacts; status/results endpoints.

## Scope
- `/pipeline/run` (POST), `/status`, `/results`, `/artifact?path=` streaming.
- Tidy models in `contracts/` and thin route handlers.
- Orchestrator calls service `main.py` entries only.

## Deliverables
- End-to-end pipeline kicks off and returns artifacts & pass job paths.
- Streaming endpoint with chunked file transfer.

## Acceptance Criteria
- E2E run on sample PDF completes with all artifacts present.
