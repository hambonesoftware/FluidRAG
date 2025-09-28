# Phase 9 — Testing Strategy & Real Data Fixtures

## Goals
- Unit tests per package; E2E pipeline test; curated fixtures (PDFs, images, json).

## Scope
- `backend/app/tests/data/{pdf,images,json}` with small curated files.
- Unit tests: parser, chunk, headers, passes, vectors, llm client (mocking).
- E2E: run pipeline and assert artifact presence/shape.

## Deliverables
- `pytest -q` green locally.
- Coverage reports optional but recommended.

## Acceptance Criteria
- All tests pass; flaky tests eliminated.
