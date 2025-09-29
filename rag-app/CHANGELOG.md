# Changelog

## [Phase 10] - 2025-10-02
### Added
- Request-scoped observability middleware emitting `X-Correlation-ID` headers, structured JSON request logs, and timing spans for the FastAPI backend.
- Configurable OpenRouter timeouts, retry backoff schedules, idle stream thresholds, and offline LLM/vector batch sizing surfaced through `backend/app/config.py` helpers.
- Stage audit enrichment across parser, chunk, header, and pass controllers with duration capture, correlation IDs, and span logging hooks.
- Comprehensive unit coverage for logging correlation context, audit helpers, OpenRouter retry logic, configuration overrides, and middleware behaviour.

### Changed
- Pipeline orchestrator now records per-stage audit metadata and writes aggregated `pipeline.audit.json` payloads, with status endpoints returning the structured audit envelope.
- Offline LLM and storage adapters respect the new tuning knobs while emitting span logs for completions and embedding batches.
- README updated with observability guidance and new environment variables governing performance tuning.

### Documentation
- Phase 10 outcome report summarising observability additions, test coverage, and configuration changes.

### Verification
- Pytest suite extended with correlation/middleware coverage while preserving offline determinism; lint, mypy, and coverage gates remain enforced.

## [Phase 9] - 2025-10-01
### Added
- Curated backend test fixtures under `backend/app/tests/data/` including an engineering text sample
  that materialises into a pseudo-PDF at runtime plus JSON expectations leveraged by the new Phase 9
  suites.
- Shared pytest `conftest.py` to isolate artifact roots, enforce offline mode, and expose fixture
  helpers for the pipeline tests.
- Comprehensive backend tests exercising upload normalization, parser enrichment, chunking,
  header join, RAG passes, and the orchestrator endpoint against the curated fixture.
- Expanded unit coverage for storage adapters, hybrid vector retrieval, pass manifest routes,
  route-level error handling, identifier helpers, and the offline LLM client to harden edge cases.

### Changed
- End-to-end pipeline test now runs the real orchestrator stack and verifies status/results
  responses plus artifact streaming using the curated document.
- Existing unit tests were refactored to rely on reusable fixtures, improving determinism and
  asserting richer invariants across the pipeline stages.

### Fixed
- Route packages now explicitly re-export their service helpers to satisfy strict mypy checks and
  clarify the functions exercised by the new route error tests.
- Vector adapter persistence tests compare floats via `math.isclose` so type checking remains
  strict without losing numerical robustness.

### Documentation
- README updated with guidance for running the full pipeline using the curated fixture, refreshed
  test/coverage commands, and a description of the new data assets.
- Recorded scope and outcomes in `PHASE_9_SCOPE.lock` and `reports/phase_9_outcome.md`.

### Verification
- Backend pytest suite expanded to 96 passing tests covering phases 1–9 with 91% line coverage
  across `backend/app`, run with `-W error`.
- Ruff, mypy (`--strict`), and pytest coverage reports executed to satisfy repo quality bars during
  the audit.

## [Phase 8] - 2025-09-30
### Added
- Frontend MVVM dashboard with upload controls, pipeline status polling, and pass result rendering.
- Artifact download UX wired to `/pipeline/artifacts` with offline awareness and DOM event signaling.
- Node-backed pytest suite exercising the PipelineVM polling loop and ResultsView artifact handling.

### Changed
- Refreshed static frontend markup and styling to support live progress indicators, pass metadata, and offline banners.
- API client extended with artifact URL helper and richer JSON fallback handling.

### Documentation
- README instructions for the new dashboard workflow and offline behavior.

### Verification
- **Features:** Completed Phase 8 audit confirming MVVM models, view-models, and views match the
  plan; traceability captured in `reports/phase_8_verification.md`.
- **Fixes:** Added pytest markers for phases 7–8, switched FastAPI startup/shutdown hooks to the
  lifespan API to eliminate deprecation warnings, and made normalization manifests emit
  timezone-aware timestamps.
- **Migrations:** Not applicable.
- **Compatibility:** Backend test suite now runs with `-W error`; Node.js remains required for the
  frontend harness.

## [Phase 7] - 2025-09-29
### Added
- Pipeline orchestrator FastAPI routes for `/pipeline/run`, `/pipeline/status/{doc_id}`, `/pipeline/results/{doc_id}`, and `/pipeline/artifacts` with audit emission and artifact streaming security.
- Validation of pass manifests/results using the domain contracts to guarantee consistent response shapes.
- Unit test coverage for orchestrator flows including success, validation, error, and streaming scenarios.

### Changed
- Hardened artifact streaming to restrict access to the configured `ARTIFACT_ROOT` and surface decoded audit information through the status endpoint.

### Documentation
- README instructions for triggering the orchestrator endpoints and retrieving streamed artifacts.

### Verification
- Confirmed orchestrator endpoints, artifact streaming guards, and associated tests align with Phase 7 plans during audit (see reports/phase_7_verification.md).
