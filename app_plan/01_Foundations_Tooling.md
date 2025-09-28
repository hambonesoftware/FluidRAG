# Phase 1 — Project Foundations & Tooling

## Goals
- Establish repo structure, venv workflow, lint/format/testing baseline.
- Enforce file size ≤ 500 lines and SoC checks.

## Scope
- Directory tree under `backend/`, `frontend/`, `data/`.
- `.gitignore`, `requirements.txt`, `ruff` + `black` config, `pytest` setup.
- Pre-commit hook to fail commits where any source file > 500 lines.

## Deliverables
- Project boots with `python run.py` (FastAPI + static frontend server).
- CI job for lint+test (optional local runner).

## Acceptance Criteria
- `ruff` and `black` produce no errors.
- `pytest -q` runs at least placeholder tests (will be replaced later).

## Risks
- Over-strict checks blocking dev → provide `--fix` guidance and exemptions for generated code.
